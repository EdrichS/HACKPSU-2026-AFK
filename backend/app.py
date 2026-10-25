"""The Nametags API: the setup routes on Postgres + pgvector, the enrollment wizard, the /live
socket, and Nova.

Every route does its slow work (decoding, embedding) before taking a connection, runs its
database calls in one `with pool.connection()` block (one transaction), deletes any file it just
wrote if that block fails, and deletes files it no longer needs only after the commit.

The face and voice embedders are the real ones (embedders/) unless NAMETAGS_EMBEDDERS=fake, which
the tests set (the mock builds its fakes itself). The context owner's router (notes, conversation,
facts) lives in backend/context_routes.py and is mounted here with app.include_router.
"""

import io
import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from psycopg import errors

from contract.audio import check_wav
from contract.embedders import FaceDetection
from contract.setup_api import (
    LOCAL_ORIGIN_REGEX,
    PHOTO_FORMATS,
    AssignIn,
    Person,
    PersonIn,
    PersonPatch,
    PhotoOut,
    VoiceOut,
    VoiceSample,
)
from db import people, photos, voice
from db.connect import DEFAULT_URL, check_embedders, open_pool
from db.errors import Conflict, NotFound
from enroll import store

log = logging.getLogger("backend")
if not logging.getLogger().handlers:  # uvicorn configures only its own loggers; ours would be silent
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

# uvicorn shows only its own info lines. Let the time to name someone through (live/presence.py)
# and keep the rest at warnings, so captions stay out of the server's log.
logging.basicConfig(format="%(name)s: %(message)s")
logging.getLogger("live.presence").setLevel(logging.INFO)

EXIF_ORIENTATION = 0x0112


DEFAULT_VOICE_CUTOFF = 0.62  # cosine distance; a match must be this close to be named outright


class TakeTurns:
    """A face embedder that detects for one caller at a time.

    dlib's face detector keeps the image it is scanning inside one shared object and releases the
    GIL while it runs, and requests arrive on several threads (the route thread pool, /live's
    worker threads), so two detections at once could corrupt each other.
    """

    def __init__(self, embedder):
        self.embedder = embedder
        self._lock = threading.Lock()

    @property
    def spec(self):
        return self.embedder.spec

    def detect_faces(self, image: bytes) -> list[FaceDetection]:
        with self._lock:
            return self.embedder.detect_faces(image)


def make_embedders():
    """The real face and voice embedders, or the contract's fakes with NAMETAGS_EMBEDDERS=fake."""
    if os.environ.get("NAMETAGS_EMBEDDERS", "real").lower() == "fake":
        from contract.fakes import FakeFaceEmbedder, FakeVoiceEmbedder

        return TakeTurns(FakeFaceEmbedder()), FakeVoiceEmbedder()
    from embedders.face import FaceRecEmbedder
    from embedders.voice import VoiceRecEmbedder

    # Live room audio sits farther from the sign-up recording than a clean clip does; a wider
    # cutoff than the model's own (0.55) names people sooner. The margin and rescue rules in
    # live/voices.py still refuse a voice two people could be. NAMETAGS_VOICE_CUTOFF tunes it.
    cutoff = float(os.environ.get("NAMETAGS_VOICE_CUTOFF") or DEFAULT_VOICE_CUTOFF)
    return TakeTurns(FaceRecEmbedder()), VoiceRecEmbedder(threshold=round(1.0 - cutoff, 4))


def load_transcriber():
    """Local speech-to-text for captions, if its model is there (NAMETAGS_TRANSCRIBE=0 turns it off)."""
    if os.environ.get("NAMETAGS_TRANSCRIBE", "1") == "0":
        return None
    try:
        from voice_rec.transcriber import Transcriber

        return Transcriber()
    except (FileNotFoundError, ImportError) as e:
        log.warning("no transcription: %s", e)
        return None


def load_claude():
    """The Anthropic client for Nova, when a key is in the environment or .env."""
    from live.cli import load_env

    load_env()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.warning("no ANTHROPIC_API_KEY: no Nova")
        return None
    import anthropic

    return anthropic.Anthropic()


def speechmatics_key() -> str | None:
    """The key for live cloud captions (backend/cloud_captions.py); None keeps captions local."""
    from backend.cloud_captions import configured_key

    key = configured_key()
    if key:
        log.info("live captions: Speechmatics real-time (audio from /live is streamed to the service)")
    else:
        log.info("live captions: local model (set SPEECHMATICS_API_KEY for word-by-word cloud captions)")
    return key


def context_ready() -> bool:
    """Whether notes and visits can become facts and cards: backend.context_ai needs the Anthropic key Nova uses."""
    from backend import context_ai

    if not context_ai.configured():
        log.warning("no ANTHROPIC_API_KEY: notes are stored as typed and visits are not summarized")
        return False
    return True


face_embedder, voice_embedder = make_embedders()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = open_pool(os.environ.get("DATABASE_URL", DEFAULT_URL))
    try:
        with pool.connection() as conn:
            check_embedders(conn, face_embedder.spec, voice_embedder.spec)
        app.state.pool = pool
        app.state.data_dir = Path(os.environ.get("NAMETAGS_DATA", "data"))
        app.state.face_embedder = face_embedder
        app.state.voice_embedder = voice_embedder
        app.state.transcriber = load_transcriber()
        app.state.claude = load_claude()
        app.state.context_ready = context_ready()
        app.state.speechmatics_key = speechmatics_key()
        app.state.presence = None  # the latest /live connection's, for /nova/ask
        yield
    finally:
        pool.close()


app = FastAPI(title="Nametags backend", lifespan=lifespan)

_origins = [o.strip() for o in os.environ.get("NAMETAGS_CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:  # deployed: the UI's origins, or * for any
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])
else:  # this laptop only
    app.add_middleware(CORSMiddleware, allow_origin_regex=LOCAL_ORIGIN_REGEX, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(NotFound)
async def _not_found(request: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse({"detail": f"No such {exc}"}, status_code=404)


@app.exception_handler(Conflict)
async def _conflict(request: Request, exc: Conflict) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(errors.CheckViolation)
async def _check_violation(request: Request, exc: errors.CheckViolation) -> JSONResponse:
    return JSONResponse({"detail": "A name or relationship can't be blank."}, status_code=422)


def _new_file(request: Request, folder: str, extension: str, data: bytes) -> Path:
    """Write `data` under a fresh random name; never overwrites anything."""
    path = request.app.state.data_dir / folder / f"{uuid.uuid4().hex}.{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as f:
        f.write(data)
    return path


def _upright(data: bytes) -> tuple[bytes, str, int, int]:
    """The photo with its EXIF rotation applied, its file extension, and its width and height."""
    try:
        image = Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        raise HTTPException(422, "Photos must be JPEG or PNG.") from None
    if image.format not in PHOTO_FORMATS:
        raise HTTPException(422, "Photos must be JPEG or PNG.")
    extension = PHOTO_FORMATS[image.format]
    if image.getexif().get(EXIF_ORIENTATION, 1) != 1:
        upright = ImageOps.exif_transpose(image)
        buf = io.BytesIO()
        upright.save(buf, "PNG" if extension == "png" else "JPEG", quality=95)  # an MPO becomes a plain JPEG
        return buf.getvalue(), extension, upright.width, upright.height
    return data, extension, image.width, image.height


@app.get("/health")
def health(request: Request) -> dict:
    state = request.app.state
    with state.pool.connection() as conn:
        conn.execute("SELECT 1")
    return {
        "status": "ok",
        "face_model": face_embedder.spec.model,
        "voice_model": voice_embedder.spec.model,
        "transcription": state.transcriber is not None,
        "captions": "speechmatics" if state.speechmatics_key else ("local" if state.transcriber is not None else "off"),
        "context": state.context_ready,  # notes and visit summaries (facts + cards)
        "claude": state.claude is not None,  # Nova
    }


@app.get("/user")
def get_user(request: Request) -> Person:
    """The app's user, the person wearing the glasses (registered with relationship 'user')."""
    with request.app.state.pool.connection() as conn:
        user = store.find_user(conn)
    if user is None:
        raise NotFound("user")
    return user


@app.get("/people")
def list_people(request: Request) -> list[Person]:
    with request.app.state.pool.connection() as conn:
        return people.list_people(conn)


@app.get("/people/{person_id}")
def get_person(request: Request, person_id: int) -> Person:
    with request.app.state.pool.connection() as conn:
        person = people.get_person(conn, person_id)
    if person is None:
        raise NotFound("person")
    return person


@app.post("/people", status_code=201)
def create_person(request: Request, body: PersonIn) -> Person:
    with request.app.state.pool.connection() as conn:
        return people.create_person(conn, body.name, body.relationship)


@app.patch("/people/{person_id}")
def update_person(request: Request, person_id: int, body: PersonPatch) -> Person:
    with request.app.state.pool.connection() as conn:
        person = people.update_person(
            conn, person_id, name=body.name, relationship=body.relationship, small_context=body.small_context
        )
    if person is None:
        raise NotFound("person")
    return person


@app.delete("/people/{person_id}", status_code=204)
def delete_person(request: Request, person_id: int) -> Response:
    with request.app.state.pool.connection() as conn:
        files = people.delete_person(conn, person_id)
    if files is None:
        raise NotFound("person")
    for path in files:  # recordings and now-faceless photos, only after the commit
        Path(path).unlink(missing_ok=True)
    return Response(status_code=204)


@app.post("/photos", status_code=201)
def upload_photo(request: Request, file: UploadFile) -> PhotoOut:
    data, extension, width, height = _upright(file.file.read())
    faces = face_embedder.detect_faces(data)
    path = _new_file(request, "photos", extension, data)
    try:
        with request.app.state.pool.connection() as conn:
            return photos.save_photo(conn, str(path), width, height, faces, face_embedder.spec.model)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


@app.get("/photos")
def list_photos(request: Request) -> list[PhotoOut]:
    with request.app.state.pool.connection() as conn:
        return photos.list_photos(conn)


@app.get("/photos/{photo_id}/image")
def photo_image(request: Request, photo_id: int) -> FileResponse:
    with request.app.state.pool.connection() as conn:
        path = photos.photo_file(conn, photo_id)
    if path is None or not Path(path).is_file():  # the row outlived its file (a cleaned data folder)
        raise NotFound("photo")
    return FileResponse(path)


@app.delete("/photos/{photo_id}", status_code=204)
def delete_photo(request: Request, photo_id: int) -> Response:
    """Remove a photo and every face in it: a shot with no face, or a sign-up that failed halfway."""
    with request.app.state.pool.connection() as conn:
        path = photos.delete_photo(conn, photo_id)
    if path is None:
        raise NotFound("photo")
    Path(path).unlink(missing_ok=True)  # only after the commit
    return Response(status_code=204)


@app.post("/faces/{face_id}/assign", status_code=204)
def assign_face(request: Request, face_id: int, body: AssignIn) -> Response:
    with request.app.state.pool.connection() as conn:
        photos.assign_face(conn, face_id, body.person_id)
    return Response(status_code=204)


@app.post("/people/{person_id}/voice", status_code=201)
def upload_voice(request: Request, person_id: int, file: UploadFile) -> VoiceOut:
    data = file.file.read()
    try:
        check_wav(data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    from backend.enroll_api import voice_clips

    clips = voice_clips(data, voice_embedder)  # the whole recording, then each 4-second slice
    written, sample_id = [], None
    try:
        with request.app.state.pool.connection() as conn:
            for clip, embedding in clips:
                path = _new_file(request, "voice", "wav", clip)
                written.append(path)
                sid = voice.add_voice(conn, person_id, str(path), embedding, voice_embedder.spec.model)
                sample_id = sample_id if sample_id is not None else sid
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return VoiceOut(voice_sample_id=sample_id)


@app.get("/people/{person_id}/voice")
def list_voice(request: Request, person_id: int) -> list[VoiceSample]:
    with request.app.state.pool.connection() as conn:
        if people.get_person(conn, person_id) is None:
            raise NotFound("person")
        return voice.list_voice(conn, person_id)


@app.get("/people/{person_id}/voice/{voice_sample_id}/audio")
def voice_audio(request: Request, person_id: int, voice_sample_id: int) -> FileResponse:
    """The recording itself (16 kHz mono WAV), to play back in the management view."""
    with request.app.state.pool.connection() as conn:
        path = voice.voice_file(conn, person_id, voice_sample_id)
    if path is None or not Path(path).is_file():
        raise NotFound("voice")
    return FileResponse(path, media_type="audio/wav")


@app.delete("/people/{person_id}/voice/{voice_sample_id}", status_code=204)
def delete_voice(request: Request, person_id: int, voice_sample_id: int) -> Response:
    with request.app.state.pool.connection() as conn:
        path = voice.delete_voice(conn, person_id, voice_sample_id)
    if path is None:
        raise NotFound("voice")
    Path(path).unlink(missing_ok=True)  # only after the commit
    return Response(status_code=204)


from backend.context_routes import router as context_router  # noqa: E402  (they import nothing from here)
from backend.enroll_api import router as enroll_router  # noqa: E402
from backend.live_api import router as live_router  # noqa: E402
from backend.nova_api import router as nova_router  # noqa: E402

app.include_router(context_router)
app.include_router(enroll_router)
app.include_router(live_router)
app.include_router(nova_router)

# The frontend (frontend/, built to frontend/dist) is served from here, so the pages and the API
# share one origin. The pages call /api/<route>; ApiPrefix rewrites that to /<route> for HTTP and
# the WebSocket alike, exactly as the Vite dev server's proxy does. Every path that isn't a route or
# a built file is the app's index.html, for the browser router (/visitor/..., /setup/..., /live).


class ApiPrefix:
    """ASGI middleware: /api/<path> -> /<path>."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                new = path[4:] or "/"
                # Remembered so an unknown /api/... path is a 404, never the frontend's index.html.
                scope = dict(scope, path=new, raw_path=new.encode(), state=dict(scope.get("state") or {}, api=True))
        await self.app(scope, receive, send)


app.add_middleware(ApiPrefix)

ROOT = Path(__file__).resolve().parents[1]


def frontend_dist() -> Path:
    """Where the built frontend is (NAMETAGS_FRONTEND_DIST, default frontend/dist), read per request."""
    return Path(os.environ.get("NAMETAGS_FRONTEND_DIST", str(ROOT / "frontend" / "dist")))


@app.get("/{path:path}", include_in_schema=False, response_model=None)
def frontend(path: str, request: Request) -> Response:
    if getattr(request.state, "api", False):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    dist = frontend_dist()
    index = dist / "index.html"
    if not index.is_file():
        return JSONResponse(
            {"detail": "The frontend isn't built here. For development run `npm run dev` in frontend/ (it serves "
             "http://localhost:5173 and proxies /api to this server); `npm run build` or the Docker image builds it."},
            status_code=404,
        )
    if path:
        candidate = (dist / path).resolve()
        if candidate.is_file() and dist.resolve() in candidate.parents:
            # Built assets carry a content hash in their name, so they can be cached for good.
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
    return FileResponse(index, headers={"Cache-Control": "no-cache"})  # always refetched: it names the current assets

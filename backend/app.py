"""The Nametags API: the setup routes on Postgres + pgvector, the enrollment wizard, the /live
socket, and Nova.

Every route does its slow work (decoding, embedding) before taking a connection, runs its
database calls in one `with pool.connection()` block (one transaction), deletes any file it just
wrote if that block fails, and deletes files it no longer needs only after the commit.

The face and voice embedders are the real ones (embedders/) unless NAMETAGS_EMBEDDERS=fake, which
the tests and the mock use. The context owner's router (notes, conversation, facts) lives in
backend/context_routes.py and is mounted here with app.include_router.
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

EXIF_ORIENTATION = 0x0112


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

    return TakeTurns(FaceRecEmbedder()), VoiceRecEmbedder()


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


def gemini_ready() -> bool:
    """Whether notes and visits can become facts and cards (backend.gemini needs GEMINI_API_KEY)."""
    from backend import gemini

    gemini.load_env()
    if not os.environ.get("GEMINI_API_KEY"):
        log.warning("no GEMINI_API_KEY: notes are stored as typed and visits are not summarized")
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
        app.state.gemini = gemini_ready()
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
        "gemini": state.gemini,  # notes and visit summaries
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
        recordings = people.delete_person(conn, person_id)
    if recordings is None:
        raise NotFound("person")
    for path in recordings:  # only after the commit
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
    if path is None:
        raise NotFound("photo")
    return FileResponse(path)


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
    embedding = voice_embedder.embed_voice(data)
    path = _new_file(request, "voice", "wav", data)
    try:
        with request.app.state.pool.connection() as conn:
            sample_id = voice.add_voice(conn, person_id, str(path), embedding, voice_embedder.spec.model)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return VoiceOut(voice_sample_id=sample_id)


@app.get("/people/{person_id}/voice")
def list_voice(request: Request, person_id: int) -> list[VoiceSample]:
    with request.app.state.pool.connection() as conn:
        if people.get_person(conn, person_id) is None:
            raise NotFound("person")
        return voice.list_voice(conn, person_id)


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

# The rough test UI (ui/): the enrollment wizard at /ui/ and the live view at /ui/live.html.
# It exercises every route above from a browser; the product UI replaces it.
UI_DIR = Path(__file__).resolve().parents[1] / "ui"
if UI_DIR.is_dir():
    from fastapi.responses import RedirectResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/ui/")

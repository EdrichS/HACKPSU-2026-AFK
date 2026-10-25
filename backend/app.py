"""The setup routes on Postgres + pgvector.

Every route does its slow work (decoding, embedding) before taking a connection, runs its
database calls in one `with pool.connection()` block (one transaction), deletes any file it just
wrote if that block fails, and deletes files it no longer needs only after the commit.

The context owner's router (notes, conversation, facts) calls db.context and gets mounted here
with app.include_router once it exists. The live connection is not built yet.
"""

import io
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from psycopg import errors

from contract.audio import check_wav
from contract.fakes import FakeFaceEmbedder, FakeVoiceEmbedder
from contract.setup_api import AssignIn, Person, PersonIn, PersonPatch, PhotoOut, VoiceOut, VoiceSample
from db import people, photos, voice
from db.connect import DEFAULT_URL, check_embedders, open_pool
from db.errors import Conflict, NotFound

# Stand-ins until the face and voice owners' adapters exist; swapping each is one line.
face_embedder = FakeFaceEmbedder()
voice_embedder = FakeVoiceEmbedder()

EXIF_ORIENTATION = 0x0112
FORMATS = {"JPEG": "jpg", "PNG": "png"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = open_pool(os.environ.get("DATABASE_URL", DEFAULT_URL))
    try:
        with pool.connection() as conn:
            check_embedders(conn, face_embedder.spec, voice_embedder.spec)
        app.state.pool = pool
        app.state.data_dir = Path(os.environ.get("NAMETAGS_DATA", "data"))
        yield
    finally:
        pool.close()


app = FastAPI(title="Nametags backend", lifespan=lifespan)


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
    if image.format not in FORMATS:
        raise HTTPException(422, "Photos must be JPEG or PNG.")
    extension = FORMATS[image.format]
    if image.getexif().get(EXIF_ORIENTATION, 1) != 1:
        upright = ImageOps.exif_transpose(image)
        buf = io.BytesIO()
        upright.save(buf, image.format, quality=95)
        return buf.getvalue(), extension, upright.width, upright.height
    return data, extension, image.width, image.height


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

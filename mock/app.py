"""The contract's routes, served from memory with the fake embedders. No network calls."""

import io
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from contract.audio import check_wav
from contract.embedders import Box
from contract.fakes import FakeFaceEmbedder, FakeVoiceEmbedder
from contract.live import (
    Arrived,
    Error,
    Frame,
    Present,
    PresentPerson,
    TrackedFace,
    Who,
    WhoAnswer,
    arrival_text,
    parse_client,
    who_text,
)
from contract.setup_api import (
    LOCAL_ORIGIN_REGEX,
    PHOTO_FORMATS,
    AssignIn,
    ConversationIn,
    DetectedFace,
    Fact,
    NotesIn,
    Person,
    PersonIn,
    PersonPatch,
    PhotoOut,
    VoiceOut,
    VoiceSample,
)

PLACEHOLDER_CARD = "Placeholder card from the mock server. The real card comes from Claude."

app = FastAPI(title="Nametags mock")
app.add_middleware(CORSMiddleware, allow_origin_regex=LOCAL_ORIGIN_REGEX, allow_methods=["*"], allow_headers=["*"])
face_embedder = FakeFaceEmbedder()
voice_embedder = FakeVoiceEmbedder()

_people: dict[int, dict] = {}
_photos: dict[int, dict] = {}
_faces: dict[int, dict] = {}
_voices: dict[int, dict] = {}
_facts: dict[int, dict] = {}
_next_id = 0


def reset() -> None:
    """Forget everything; the test fixture calls this before each test."""
    global _next_id
    for table in (_people, _photos, _faces, _voices, _facts):
        table.clear()
    _next_id = 0


def _new_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(name: str, relationship: str) -> tuple[str, str]:
    return name.strip().lower(), relationship.strip().lower()


def _person_or_404(person_id: int) -> dict:
    if person_id not in _people:
        raise HTTPException(404, "No such person")
    return _people[person_id]


def _person_out(person_id: int) -> Person:
    p = _people[person_id]
    return Person(
        id=person_id,
        name=p["name"],
        relationship=p["relationship"],
        face_count=sum(1 for f in _faces.values() if f["person_id"] == person_id),
        has_voice=any(v["person_id"] == person_id for v in _voices.values()),
        small_context=p["small_context"],
    )


def _refuse_duplicate(name: str, relationship: str, except_id: int | None = None) -> None:
    for pid, p in _people.items():
        if pid != except_id and _key(p["name"], p["relationship"]) == _key(name, relationship):
            raise HTTPException(409, f"There's already a {p['name']}, {p['relationship']}.")


def _photo_out(photo_id: int) -> PhotoOut:
    photo = _photos[photo_id]
    faces = [
        DetectedFace(face_id=fid, box=f["box"], person_id=f["person_id"])
        for fid, f in sorted(_faces.items())
        if f["photo_id"] == photo_id
    ]
    return PhotoOut(photo_id=photo_id, width=photo["width"], height=photo["height"], faces=faces)


def _add_fact(person_id: int, text: str, source: str) -> None:
    for f in _facts.values():
        if f["person_id"] == person_id and f["text"].strip().lower() == text.strip().lower():
            return
    _facts[_new_id()] = {"person_id": person_id, "text": text, "source": source, "created_at": _now()}


@app.get("/people")
def list_people() -> list[Person]:
    return [_person_out(pid) for pid in sorted(_people, key=lambda i: (_people[i]["name"], i))]


@app.post("/people", status_code=201)
def create_person(body: PersonIn) -> Person:
    _refuse_duplicate(body.name, body.relationship)
    pid = _new_id()
    _people[pid] = {"name": body.name, "relationship": body.relationship, "small_context": ""}
    return _person_out(pid)


@app.patch("/people/{person_id}")
def update_person(person_id: int, body: PersonPatch) -> Person:
    p = _person_or_404(person_id)
    name = body.name if body.name is not None else p["name"]
    relationship = body.relationship if body.relationship is not None else p["relationship"]
    _refuse_duplicate(name, relationship, except_id=person_id)
    p["name"], p["relationship"] = name, relationship
    if body.small_context is not None:
        p["small_context"] = body.small_context
        if body.small_context.strip():
            _add_fact(person_id, body.small_context, "notes")  # a hand-fixed card is kept as a note
    return _person_out(person_id)


@app.delete("/people/{person_id}", status_code=204)
def delete_person(person_id: int) -> Response:
    _person_or_404(person_id)
    del _people[person_id]
    for f in _faces.values():
        if f["person_id"] == person_id:
            f["person_id"] = None
    for table in (_voices, _facts):
        for row_id in [i for i, row in table.items() if row["person_id"] == person_id]:
            del table[row_id]
    return Response(status_code=204)


@app.post("/photos", status_code=201)
def upload_photo(file: UploadFile) -> PhotoOut:
    data = file.file.read()
    try:
        image = Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        raise HTTPException(422, "Photos must be JPEG or PNG.") from None
    if image.format not in PHOTO_FORMATS:
        raise HTTPException(422, "Photos must be JPEG or PNG.")
    photo_id = _new_id()
    _photos[photo_id] = {
        "data": data,
        "media_type": "image/png" if PHOTO_FORMATS[image.format] == "png" else "image/jpeg",
        "width": image.width,
        "height": image.height,
    }
    for detection in face_embedder.detect_faces(data):
        _faces[_new_id()] = {"photo_id": photo_id, "box": Box(**detection.box.model_dump()), "person_id": None}
    return _photo_out(photo_id)


@app.get("/photos")
def list_photos() -> list[PhotoOut]:
    return [_photo_out(photo_id) for photo_id in sorted(_photos)]


@app.get("/photos/{photo_id}/image")
def photo_image(photo_id: int) -> Response:
    if photo_id not in _photos:
        raise HTTPException(404, "No such photo")
    photo = _photos[photo_id]
    return Response(content=photo["data"], media_type=photo["media_type"])


@app.post("/faces/{face_id}/assign", status_code=204)
def assign_face(face_id: int, body: AssignIn) -> Response:
    if face_id not in _faces:
        raise HTTPException(404, "No such face")
    face = _faces[face_id]
    if body.person_id is not None:
        _person_or_404(body.person_id)
        for fid, other in _faces.items():
            if fid != face_id and other["photo_id"] == face["photo_id"] and other["person_id"] == body.person_id:
                raise HTTPException(
                    409, "That person is already labelled on another face in this photo. Reassign that face first."
                )
    face["person_id"] = body.person_id
    return Response(status_code=204)


@app.post("/people/{person_id}/voice", status_code=201)
def upload_voice(person_id: int, file: UploadFile) -> VoiceOut:
    data = file.file.read()
    try:
        check_wav(data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    _person_or_404(person_id)
    voice_embedder.embed_voice(data)
    sample_id = _new_id()
    _voices[sample_id] = {"person_id": person_id, "created_at": _now()}
    return VoiceOut(voice_sample_id=sample_id)


@app.get("/people/{person_id}/voice")
def list_voice(person_id: int) -> list[VoiceSample]:
    _person_or_404(person_id)
    return [
        VoiceSample(voice_sample_id=sid, created_at=v["created_at"])
        for sid, v in sorted(_voices.items())
        if v["person_id"] == person_id
    ]


@app.delete("/people/{person_id}/voice/{voice_sample_id}", status_code=204)
def delete_voice(person_id: int, voice_sample_id: int) -> Response:
    sample = _voices.get(voice_sample_id)
    if sample is None or sample["person_id"] != person_id:
        raise HTTPException(404, "No such recording")
    del _voices[voice_sample_id]
    return Response(status_code=204)


@app.post("/people/{person_id}/notes")
def add_notes(person_id: int, body: NotesIn) -> Person:
    p = _person_or_404(person_id)
    _add_fact(person_id, body.text, "notes")
    p["small_context"] = PLACEHOLDER_CARD
    return _person_out(person_id)


@app.post("/people/{person_id}/conversation")
def add_conversation(person_id: int, body: ConversationIn) -> Person:
    p = _person_or_404(person_id)
    _add_fact(person_id, "\n".join(f"{line.speaker}: {line.text}" for line in body.lines), "conversation")
    p["small_context"] = PLACEHOLDER_CARD
    return _person_out(person_id)


@app.get("/people/{person_id}/facts")
def list_facts(person_id: int) -> list[Fact]:
    _person_or_404(person_id)
    return [
        Fact(id=fid, text=f["text"], source=f["source"], created_at=f["created_at"])
        for fid, f in sorted(_facts.items(), key=lambda item: (item[1]["created_at"], item[0]))
        if f["person_id"] == person_id
    ]


@app.delete("/people/{person_id}/facts/{fact_id}", status_code=204)
def delete_fact(person_id: int, fact_id: int) -> Response:
    fact = _facts.get(fact_id)
    if fact is None or fact["person_id"] != person_id:
        raise HTTPException(404, "No such fact")
    del _facts[fact_id]
    return Response(status_code=204)


@app.websocket("/live")
async def live(ws: WebSocket) -> None:
    """One fake person is "seen" on every frame and announced on the first one."""
    await ws.accept()
    sam = PresentPerson(person_id=0, name="Sam", relationship="friend", small_context=PLACEHOLDER_CARD)
    announced = False
    try:
        while True:
            received = await ws.receive()
            if received["type"] == "websocket.disconnect":
                return
            raw = received.get("text")
            if raw is None:  # a binary frame; every contract message is JSON text
                await ws.send_text(Error(message="Messages must be JSON text: frame, audio or who.").model_dump_json())
                continue
            try:
                message = parse_client(raw)
            except ValidationError:
                await ws.send_text(Error(message="Unrecognised message; expected frame, audio or who.").model_dump_json())
                continue
            if isinstance(message, Frame):
                face = TrackedFace(box=Box(x=0, y=0, width=1, height=1), state="named", person_id=sam.person_id)
                await ws.send_text(Present(people=[sam], faces=[face]).model_dump_json())
                if not announced:
                    await ws.send_text(Arrived(person=sam, via="face", text=arrival_text(sam)).model_dump_json())
                    announced = True
            elif isinstance(message, Who):
                await ws.send_text(WhoAnswer(text=who_text([sam] if announced else [])).model_dump_json())
    except WebSocketDisconnect:
        return

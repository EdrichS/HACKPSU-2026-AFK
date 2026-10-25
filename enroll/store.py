"""Writing one person's enrollment into the database.

Everything goes through the db package, so every row follows db/schema.sql:

    people         create_person; small_context set by save_context
    photos         save_photo: one row per stored image, with the stored file's width and height
    face_samples   save_photo: one row per face found (model + vector(128)); assign_face labels one
    voice_samples  add_voice: one row per recording (model + vector(192), the WAV's path)
    facts          save_context: one row per sentence, source 'notes'

Files go where the backend puts them, NAMETAGS_DATA/photos and NAMETAGS_DATA/voice, under random
names, so GET /photos/{id}/image serves them unchanged.
"""

import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg
from PIL import Image, ImageOps, UnidentifiedImageError

from contract.audio import check_wav
from contract.embedders import FaceDetection, FaceEmbedder, VoiceEmbedder
from contract.setup_api import PHOTO_FORMATS, Person
from db import context, people, photos, voice

EXIF_ORIENTATION = 0x0112
LIMIT = context.LIMIT  # characters: the card, and each fact

# The app's user, the person wearing the glasses, is a people row too, so their voice is known
# and their lines get their name. The schema has no flag for it; the relationship column says it.
USER_RELATIONSHIP = "user"
USER_RELATIONSHIPS = {"user", "patient"}

# With several faces in a photo, label the biggest only if it is at least this many times the
# area of the next one (a selfie with people far behind). Otherwise the photo is ambiguous and is
# stored unlabelled, for the family to label in the setup UI.
DOMINANT_FACE_RATIO = 1.5

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SavedPhoto:
    photo_id: int
    path: Path
    faces_found: int
    face_id: int | None  # the face labelled as this person, or None when no face stood out


def is_user_relationship(relationship: str) -> bool:
    return relationship.strip().lower() in USER_RELATIONSHIPS


def find_user(conn: psycopg.Connection) -> Person | None:
    """The app user's row, the earliest one if there are several."""
    users = [p for p in people.list_people(conn) if is_user_relationship(p.relationship)]
    return min(users, key=lambda p: p.id) if users else None


def find_person(conn: psycopg.Connection, name: str, relationship: str) -> Person | None:
    """The person with this name and relationship, by the schema's rule: case and spaces around don't count."""
    key = (name.strip().lower(), relationship.strip().lower())
    for p in people.list_people(conn):
        if (p.name.strip().lower(), p.relationship.strip().lower()) == key:
            return p
    return None


def new_file(data_dir: Path, folder: str, extension: str, data: bytes) -> Path:
    """Write `data` under a fresh random name, as the backend does; never overwrites anything."""
    path = Path(data_dir) / folder / f"{uuid.uuid4().hex}.{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as f:
        f.write(data)
    return path


def upright(data: bytes) -> tuple[bytes, str, int, int]:
    """A JPEG or PNG with its EXIF rotation applied: (bytes, extension, width, height)."""
    try:
        image = Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        raise ValueError("Photos must be JPEG or PNG.") from None
    if image.format not in PHOTO_FORMATS:
        raise ValueError("Photos must be JPEG or PNG.")
    extension = PHOTO_FORMATS[image.format]
    if image.getexif().get(EXIF_ORIENTATION, 1) != 1:
        fixed = ImageOps.exif_transpose(image)
        buf = io.BytesIO()
        fixed.save(buf, "PNG" if extension == "png" else "JPEG", quality=95)
        return buf.getvalue(), extension, fixed.width, fixed.height
    return data, extension, image.width, image.height


def pick_face(faces: list[FaceDetection]) -> int | None:
    """Index of the face to label, or None when no single face clearly dominates."""
    if not faces:
        return None
    if len(faces) == 1:
        return 0
    areas = [f.box.width * f.box.height for f in faces]
    order = sorted(range(len(faces)), key=areas.__getitem__, reverse=True)
    if areas[order[0]] >= DOMINANT_FACE_RATIO * areas[order[1]]:
        return order[0]
    return None


def save_photo_of(
    conn: psycopg.Connection, data_dir: Path, person_id: int, image: bytes, embedder: FaceEmbedder
) -> SavedPhoto | None:
    """Store a photo and its faces, and label the dominant face as this person.

    Returns None, storing nothing, when no face is found. Raises ValueError for a file that isn't
    a JPEG or PNG. If the database refuses the rows, the file is removed again.
    """
    data, extension, width, height = upright(image)
    faces = embedder.detect_faces(data)
    if not faces:
        return None
    path = new_file(data_dir, "photos", extension, data)
    try:
        with conn.transaction():
            out = photos.save_photo(conn, str(path), width, height, faces, embedder.spec.model)
            index = pick_face(faces)
            face_id = out.faces[index].face_id if index is not None else None
            if face_id is not None:
                photos.assign_face(conn, face_id, person_id)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return SavedPhoto(photo_id=out.photo_id, path=path, faces_found=len(faces), face_id=face_id)


def save_voice_of(
    conn: psycopg.Connection, data_dir: Path, person_id: int, wav: bytes, embedder: VoiceEmbedder
) -> int:
    """Store a recording and its embedding as one voice_samples row; return the sample id.

    Raises ValueError for a WAV that breaks the contract (not 16 kHz mono 16-bit, or under a
    second). If the database refuses the row, the file is removed again.
    """
    check_wav(wav)
    embedding = embedder.embed_voice(wav)
    path = new_file(data_dir, "voice", "wav", wav)
    try:
        with conn.transaction():
            return voice.add_voice(conn, person_id, str(path), embedding, embedder.spec.model)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def split_facts(text: str, limit: int = LIMIT) -> list[str]:
    """One fact per sentence (or line), each within the schema's limit; longer ones split on a space."""
    facts = []
    for line in text.splitlines():
        for sentence in _SENTENCE_END.split(line.strip()):
            sentence = sentence.strip()
            while len(sentence) > limit:
                cut = sentence.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                facts.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                facts.append(sentence)
    return facts


def make_card(facts: list[str], limit: int = LIMIT) -> str:
    """The first facts, whole, as far as they fit in the card."""
    card = ""
    for fact in facts:
        candidate = f"{card} {fact}".strip()
        if len(candidate) > limit:
            break
        card = candidate
    return card


def save_context_of(conn: psycopg.Connection, person_id: int, text: str) -> Person:
    """Store the text as facts (source 'notes') and make the card from as much of it as fits."""
    facts = split_facts(text)
    if not facts:
        raise ValueError("The context is blank.")
    with conn.transaction():
        return context.save_context(conn, person_id, facts, "notes", make_card(facts))

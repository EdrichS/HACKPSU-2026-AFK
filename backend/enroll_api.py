"""The enrollment wizard's routes: check one photo, check the recording, then upload everything.

The wizard takes photos (step 2) and a recording (step 3) before it knows the name (step 4), so
the checks are stateless and the final POST /enroll carries it all. Rows go in through the db
package exactly as python -m enroll stores them: people, photos + one labelled face_samples row
per photo, one voice_samples row per clip (the whole recording and each 4-second slice), facts
with source 'notes' and the card in small_context.
"""

import logging
from pathlib import Path

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError

from contract.audio import check_wav
from contract.embedders import Box, FaceDetection
from contract.setup_api import Person, PersonIn
from db import people as people_db
from db import photos as photos_db
from db import voice as voice_db
from db.errors import Conflict
from embedders.voice import decode_wav, encode_wav
from enroll import store
from enroll.mic import MIN_UTTERANCE, windows
from voice_rec.config import SAMPLE_RATE

log = logging.getLogger("backend.enroll")
router = APIRouter(prefix="/enroll", tags=["enroll"])

MIN_SPEECH = 3.0  # seconds of actual speech a recording must contain
WINDOW = 4.0  # each slice this long is stored as its own sample, as python -m enroll does


class PhotoCheck(BaseModel):
    ok: bool
    faces: int
    box: Box | None = None  # the face that would be enrolled
    width: int
    height: int
    reason: str = ""


class VoiceCheck(BaseModel):
    ok: bool
    seconds: float
    speech_seconds: float
    reason: str = ""


class EnrollOut(BaseModel):
    person: Person
    photo_ids: list[int]  # GET /photos/{id}/image shows them (the first is the front shot)
    face_ids: list[int]
    voice_sample_ids: list[int]
    facts: int
    skipped_photos: list[str]  # photos with no clear face, not stored


def inspect_photo(embedder, data: bytes) -> tuple[bytes, str, int, int, list[FaceDetection], int | None]:
    """The upright photo, its extension and size, every face, and the index of the one to enroll."""
    data, extension, width, height = store.upright(data)  # ValueError for a non-image
    faces = embedder.detect_faces(data)
    return data, extension, width, height, faces, store.pick_face(faces)


def trim_speech(samples: np.ndarray) -> np.ndarray:
    """The speech in a clip with the silences cut out; empty when none of it is speech."""
    try:
        from voice_rec.vad import SpeechSegmenter

        segmenter = SpeechSegmenter()
    except FileNotFoundError as e:  # no VAD model: take the whole clip
        log.warning("no VAD (%s); taking the recording as it is", e)
        return np.asarray(samples, dtype=np.float32)
    parts = [s.samples for s in segmenter.feed(samples) + segmenter.flush() if s.duration >= MIN_UTTERANCE]
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def prepare_voice(embedder, wav: bytes) -> tuple[list[tuple[bytes, list[float]]], float, float]:
    """(clips as (wav bytes, embedding), seconds, speech seconds). ValueError says what's wrong."""
    check_wav(wav)
    samples = decode_wav(wav)
    seconds = len(samples) / SAMPLE_RATE
    speech = trim_speech(samples)
    speech_seconds = len(speech) / SAMPLE_RATE
    if speech_seconds < MIN_SPEECH:
        raise ValueError(
            f"We heard {speech_seconds:.0f} seconds of speech; please read the whole text out loud "
            f"(at least {MIN_SPEECH:.0f} seconds)."
        )
    clips = [speech] + windows(speech, WINDOW)
    prepared = []
    for clip in clips:
        data = encode_wav(clip)
        prepared.append((data, embedder.embed_voice(data)))
    return prepared, seconds, speech_seconds


@router.post("/check/photo")
def check_photo(request: Request, file: UploadFile) -> PhotoCheck:
    """Is this a usable enrollment photo: exactly one clear face? For the wizard's per-shot feedback."""
    try:
        _, _, width, height, faces, index = inspect_photo(request.app.state.face_embedder, file.file.read())
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    if not faces:
        return PhotoCheck(ok=False, faces=0, width=width, height=height, reason="We couldn't find a face. Keep your face inside the oval and try again.")
    if index is None:
        return PhotoCheck(ok=False, faces=len(faces), width=width, height=height, reason="More than one face is in the picture. Just you, please.")
    return PhotoCheck(ok=True, faces=len(faces), box=faces[index].box, width=width, height=height)


@router.post("/check/voice")
def check_voice(request: Request, file: UploadFile) -> VoiceCheck:
    """Is this recording usable: the contract's WAV format, with enough speech in it?"""
    data = file.file.read()
    try:
        check_wav(data)
    except ValueError as e:
        return VoiceCheck(ok=False, seconds=0.0, speech_seconds=0.0, reason=str(e))
    samples = decode_wav(data)
    speech_seconds = len(trim_speech(samples)) / SAMPLE_RATE
    seconds = len(samples) / SAMPLE_RATE
    if speech_seconds < MIN_SPEECH:
        return VoiceCheck(ok=False, seconds=seconds, speech_seconds=speech_seconds, reason=f"We heard {speech_seconds:.0f} seconds of speech; please read the whole text out loud.")
    return VoiceCheck(ok=True, seconds=seconds, speech_seconds=speech_seconds)


@router.post("", status_code=201)
def enroll(
    request: Request,
    name: str = Form(...),
    relationship: str = Form(..., description="son, daughter, ... or 'user' for the person wearing the glasses"),
    notes: str = Form("", description="anything the user should know; a sentence per fact"),
    merge: bool = Form(False, description="add these samples to an existing person with the same name and relationship instead of refusing"),
    photos: list[UploadFile] = File(default=[]),
    voice: UploadFile | None = File(default=None),
) -> EnrollOut:
    """The wizard's Upload: name, relationship, notes, the photos and the recording, in one go."""
    try:
        PersonIn(name=name, relationship=relationship)
    except ValidationError:
        raise HTTPException(422, "The name must be 1-80 characters and the relationship 1-40.") from None
    state = request.app.state

    prepared_photos, skipped = [], []
    for upload in photos:
        try:
            data, extension, width, height, faces, index = inspect_photo(state.face_embedder, upload.file.read())
        except ValueError as e:
            skipped.append(f"{upload.filename}: {e}")
            continue
        if index is None:
            skipped.append(f"{upload.filename}: {'no face found' if not faces else 'more than one face'}")
            continue
        prepared_photos.append((data, extension, width, height, faces, index))
    if photos and not prepared_photos:
        raise HTTPException(422, "None of the photos shows one clear face. " + " ".join(skipped))

    clips = []
    if voice is not None:
        try:
            clips, _, _ = prepare_voice(state.voice_embedder, voice.file.read())
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    written: list[Path] = []
    try:
        with state.pool.connection() as conn:
            existing = store.find_person(conn, name, relationship)
            if existing is not None and not merge:
                raise Conflict(f"There's already a {name.strip()}, {relationship.strip()}. Send merge=true to add to them.")
            person = existing or people_db.create_person(conn, name, relationship)
            photo_ids, face_ids = [], []
            for data, extension, width, height, faces, index in prepared_photos:
                path = store.new_file(state.data_dir, "photos", extension, data)
                written.append(path)
                out = photos_db.save_photo(conn, str(path), width, height, faces, state.face_embedder.spec.model)
                face_id = out.faces[index].face_id
                photos_db.assign_face(conn, face_id, person.id)
                photo_ids.append(out.photo_id)
                face_ids.append(face_id)
            sample_ids = []
            for data, embedding in clips:
                path = store.new_file(state.data_dir, "voice", "wav", data)
                written.append(path)
                sample_ids.append(voice_db.add_voice(conn, person.id, str(path), embedding, state.voice_embedder.spec.model))
            facts = 0
            if notes.strip():
                person = store.save_context_of(conn, person.id, notes)
                facts = len(store.split_facts(notes))
            else:
                person = people_db.get_person(conn, person.id)
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return EnrollOut(person=person, photo_ids=photo_ids, face_ids=face_ids, voice_sample_ids=sample_ids, facts=facts, skipped_photos=skipped)

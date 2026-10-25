"""enroll.store writes rows the way db/schema.sql wants them, through the db package."""

import pytest

from contract.embedders import Box, FaceDetection
from contract.fakes import FakeFaceEmbedder, FakeVoiceEmbedder, make_wav
from db.context import list_facts
from db.errors import NotFound
from db.people import create_person, get_person
from db.photos import list_photos
from db.voice import list_voice
from enroll import store
from tests.helpers import png_bytes


@pytest.fixture
def david(conn) -> int:
    return create_person(conn, "David", "grandson").id


def files_under(folder) -> list:
    """Files only: a folder left behind by a rolled-back write is fine."""
    return [p for p in folder.rglob("*") if p.is_file()]


def test_find_person_ignores_case_and_spaces(conn, david):
    assert store.find_person(conn, " david ", "GRANDSON").id == david
    assert store.find_person(conn, "Maria", "daughter") is None


def test_photo_face_is_labelled_as_the_person(conn, david, tmp_path):
    saved = store.save_photo_of(conn, tmp_path, david, png_bytes(40, 30), FakeFaceEmbedder())
    assert saved.faces_found == 1 and saved.face_id is not None
    assert saved.path.exists() and saved.path.parent == tmp_path / "photos"
    [photo] = list_photos(conn)
    assert (photo.photo_id, photo.width, photo.height) == (saved.photo_id, 40, 30)
    assert [(f.face_id, f.person_id) for f in photo.faces] == [(saved.face_id, david)]
    assert get_person(conn, david).face_count == 1
    model, = conn.execute("SELECT model FROM face_samples WHERE id = %s", (saved.face_id,)).fetchone()
    assert model == "fake-face"


def test_photo_without_a_face_is_not_stored(conn, david, tmp_path):
    class NoFaces(FakeFaceEmbedder):
        def detect_faces(self, image):
            return []

    assert store.save_photo_of(conn, tmp_path, david, png_bytes(4, 4), NoFaces()) is None
    assert list_photos(conn) == []
    assert list(tmp_path.rglob("*")) == []


def test_photo_with_two_similar_faces_is_stored_unlabelled(conn, david, tmp_path):
    class TwoFaces(FakeFaceEmbedder):
        def detect_faces(self, image):
            one = super().detect_faces(image)[0]
            return [one, FaceDetection(box=Box(x=1, y=1, width=1, height=1), embedding=one.embedding)]

    saved = store.save_photo_of(conn, tmp_path, david, png_bytes(4, 4), TwoFaces())
    assert (saved.faces_found, saved.face_id) == (2, None)
    [photo] = list_photos(conn)
    assert [f.person_id for f in photo.faces] == [None, None]
    assert get_person(conn, david).face_count == 0


def test_the_dominant_face_is_the_one_labelled(conn, david, tmp_path):
    class Selfie(FakeFaceEmbedder):
        def detect_faces(self, image):
            e = super().detect_faces(image)[0].embedding
            small = FaceDetection(box=Box(x=0, y=0, width=1, height=1), embedding=e)
            big = FaceDetection(box=Box(x=1, y=1, width=3, height=3), embedding=e)
            return [small, big]

    saved = store.save_photo_of(conn, tmp_path, david, png_bytes(4, 4), Selfie())
    [photo] = list_photos(conn)
    [labelled] = [f for f in photo.faces if f.person_id == david]
    assert (labelled.face_id, labelled.box.width) == (saved.face_id, 3)


def test_rotated_phone_photo_is_stored_upright(conn, david, tmp_path):
    import io

    from PIL import Image

    img, exif, buf = Image.new("RGB", (4, 3)), Image.Exif(), io.BytesIO()
    exif[0x0112] = 6  # EXIF orientation: rotate 90 degrees
    img.save(buf, "JPEG", exif=exif)
    saved = store.save_photo_of(conn, tmp_path, david, buf.getvalue(), FakeFaceEmbedder())
    [photo] = list_photos(conn)
    assert (photo.width, photo.height) == (3, 4)
    assert Image.open(saved.path).size == (3, 4)


def test_not_an_image_is_rejected_and_leaves_no_file(conn, david, tmp_path):
    with pytest.raises(ValueError, match="JPEG or PNG"):
        store.save_photo_of(conn, tmp_path, david, b"not an image", FakeFaceEmbedder())
    assert list(tmp_path.rglob("*")) == []


def test_voice_sample_is_stored_with_its_file(conn, david, tmp_path):
    sample_id = store.save_voice_of(conn, tmp_path, david, make_wav(2.0), FakeVoiceEmbedder())
    assert [s.voice_sample_id for s in list_voice(conn, david)] == [sample_id]
    [wav] = list((tmp_path / "voice").glob("*.wav"))
    row = conn.execute("SELECT audio_path, model FROM voice_samples WHERE id = %s", (sample_id,)).fetchone()
    assert row == (str(wav), "fake-voice")
    assert get_person(conn, david).has_voice


def test_voice_for_a_missing_person_leaves_no_file(conn, tmp_path):
    with pytest.raises(NotFound, match="person"):
        store.save_voice_of(conn, tmp_path, 999, make_wav(2.0), FakeVoiceEmbedder())
    assert files_under(tmp_path) == []


def test_a_short_or_wrong_wav_is_rejected(conn, david, tmp_path):
    with pytest.raises(ValueError, match="1 second"):
        store.save_voice_of(conn, tmp_path, david, make_wav(0.5), FakeVoiceEmbedder())
    with pytest.raises(ValueError, match="16 kHz"):
        store.save_voice_of(conn, tmp_path, david, b"not a wav", FakeVoiceEmbedder())
    assert files_under(tmp_path) == []


def test_context_becomes_facts_and_a_card(conn, david):
    text = "David is your grandson. He just moved to Pittsburgh.\nHe works as a nurse."
    person = store.save_context_of(conn, david, text)
    assert person.small_context == "David is your grandson. He just moved to Pittsburgh. He works as a nurse."
    facts = list_facts(conn, david)
    assert [f.text for f in facts] == ["David is your grandson.", "He just moved to Pittsburgh.", "He works as a nurse."]
    assert {f.source for f in facts} == {"notes"}


def test_long_context_keeps_the_card_and_facts_within_the_limits(conn, david):
    text = " ".join(f"Fact number {i} about this person, which is a full sentence." for i in range(30))
    person = store.save_context_of(conn, david, text)
    assert 0 < len(person.small_context) <= store.LIMIT
    assert person.small_context.endswith("sentence.")  # whole sentences only
    assert all(len(f.text) <= store.LIMIT for f in list_facts(conn, david))


def test_one_huge_sentence_is_split_on_spaces():
    text = ("word " * 200).strip()
    facts = store.split_facts(text)
    assert len(facts) > 1
    assert all(len(f) <= store.LIMIT for f in facts)
    assert " ".join(facts) == text


def test_blank_context_is_rejected(conn, david):
    with pytest.raises(ValueError, match="blank"):
        store.save_context_of(conn, david, "  \n ")
    assert list_facts(conn, david) == []

import pytest

from db.errors import NotFound
from db.people import create_person
from db.voice import add_voice, delete_voice, list_voice
from tests.helpers import vec


def test_recording_again_keeps_both_samples(conn):
    pid = create_person(conn, "David", "grandson").id
    first = add_voice(conn, pid, "data/voice/1.wav", vec(1.0, dims=192), "test")
    second = add_voice(conn, pid, "data/voice/2.wav", vec(0.0, 1.0, dims=192), "test")
    assert [s.voice_sample_id for s in list_voice(conn, pid)] == [first, second]


def test_voice_for_unknown_person(conn):
    with pytest.raises(NotFound, match="person"):
        add_voice(conn, 999, "data/voice/x.wav", vec(1.0, dims=192), "test")


def test_deleting_one_recording(conn):
    pid = create_person(conn, "David", "grandson").id
    first = add_voice(conn, pid, "data/voice/1.wav", vec(1.0, dims=192), "test")
    add_voice(conn, pid, "data/voice/2.wav", vec(0.0, 1.0, dims=192), "test")
    assert delete_voice(conn, pid, first) == "data/voice/1.wav"
    assert len(list_voice(conn, pid)) == 1


def test_someone_elses_recording_is_not_found(conn):
    david = create_person(conn, "David", "grandson").id
    maria = create_person(conn, "Maria", "daughter").id
    sample = add_voice(conn, david, "data/voice/1.wav", vec(1.0, dims=192), "test")
    assert delete_voice(conn, maria, sample) is None

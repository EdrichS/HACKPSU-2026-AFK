import pytest

from db.errors import Conflict
from db.people import create_person, delete_person, get_person, list_people, update_person
from tests.helpers import insert_face, insert_photo, insert_voice


def test_person_without_faces_counts_zero(conn):                       # Review Focus 3
    create_person(conn, "David", "grandson")
    assert list_people(conn)[0].face_count == 0          # COUNT(*) under the LEFT JOIN would say 1


def test_counts_do_not_multiply(conn):
    pid = create_person(conn, "David", "grandson").id
    insert_face(conn, insert_photo(conn), person_id=pid)
    insert_face(conn, insert_photo(conn), person_id=pid)
    insert_voice(conn, pid)
    insert_voice(conn, pid)
    p = get_person(conn, pid)
    assert (p.face_count, p.has_voice) == (2, True)


def test_partial_update_keeps_the_other_fields(conn):
    pid = create_person(conn, "David", "grandson").id
    p = update_person(conn, pid, relationship="great-grandson")
    assert (p.name, p.relationship, p.small_context) == ("David", "great-grandson", "")


def test_card_edit_is_kept_as_a_note(conn):
    pid = create_person(conn, "David", "grandson").id
    update_person(conn, pid, small_context="David is your grandson. He is a nurse.")
    rows = conn.execute("SELECT text, source FROM facts").fetchall()
    assert rows == [("David is your grandson. He is a nurse.", "notes")]


def test_missing_person(conn):
    assert get_person(conn, 999) is None
    assert update_person(conn, 999, name="X") is None
    assert delete_person(conn, 999) is None


def test_list_is_ordered_by_name(conn):
    for name in ["Maria", "David", "Ana"]:
        create_person(conn, name, "family")
    assert [p.name for p in list_people(conn)] == ["Ana", "David", "Maria"]


def test_same_name_and_relationship_is_refused(conn):
    create_person(conn, "David", "grandson")
    with pytest.raises(Conflict):
        create_person(conn, " david", "Grandson")


def test_delete_returns_the_recordings_to_remove(conn):
    pid = create_person(conn, "David", "grandson").id
    insert_voice(conn, pid, audio_path="data/voice/a.wav")
    assert delete_person(conn, pid) == ["data/voice/a.wav"]

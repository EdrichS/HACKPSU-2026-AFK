import psycopg
import pytest

from contract.embedders import EmbedderSpec
from contract.fakes import FakeFaceEmbedder, FakeVoiceEmbedder
from db.connect import DatabaseUnavailable, EmbedderMismatch, check_embedders, open_pool
from tests.helpers import insert_face, insert_fact, insert_person, insert_photo, insert_voice, vec


@pytest.mark.parametrize("blank", ["  ", "\t", " \n "])
def test_blank_names_are_rejected(conn, blank):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO people (name, relationship) VALUES (%s, 'grandson')", (blank,))


def test_wrong_dimensions_are_rejected(conn):
    with pytest.raises(psycopg.DataError, match="expected 128 dimensions"):
        insert_face(conn, insert_photo(conn), embedding=vec(1.0, dims=127))


def test_nan_is_rejected(conn):
    with pytest.raises(psycopg.DataError, match="NaN"):
        insert_face(conn, insert_photo(conn), embedding=vec(float("nan"), dims=128))


def test_zero_vector_is_rejected(conn):
    pid = insert_person(conn, "David", "grandson")
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_voice(conn, pid, embedding=vec(dims=192))


def test_deleting_a_photo_deletes_its_faces(conn):
    photo_id = insert_photo(conn)
    insert_face(conn, photo_id)
    conn.execute("DELETE FROM photos WHERE id = %s", (photo_id,))
    assert conn.execute("SELECT count(*) FROM face_samples").fetchone() == (0,)


def test_deleting_a_person_unlabels_faces_and_drops_the_rest(conn):
    pid = insert_person(conn, "David", "grandson")
    insert_face(conn, insert_photo(conn), person_id=pid)
    insert_voice(conn, pid)
    insert_fact(conn, pid)
    conn.execute("DELETE FROM people WHERE id = %s", (pid,))
    assert conn.execute("SELECT person_id FROM face_samples").fetchall() == [(None,)]
    counts = "SELECT (SELECT count(*) FROM voice_samples), (SELECT count(*) FROM facts)"
    assert conn.execute(counts).fetchone() == (0, 0)


def test_open_pool_names_the_fix_when_postgres_is_down():
    with pytest.raises(DatabaseUnavailable, match="docker compose up -d --wait db"):
        open_pool("postgresql://nametags:nametags@localhost:1/nametags", timeout=1)


def test_check_embedders_catches_a_size_mismatch(conn):
    bigger = EmbedderSpec(dimensions=512, metric="cosine", cutoff=0.75, model="bigger-voice")
    with pytest.raises(EmbedderMismatch, match=r"vector\(192\)") as caught:
        check_embedders(conn, FakeFaceEmbedder().spec, bigger)
    # A reset alone recreates vector(192); the message must name the schema edit first.
    assert "vector(512) in db/schema.sql" in str(caught.value)


def test_check_embedders_catches_samples_from_another_model(conn):
    insert_face(conn, insert_photo(conn), model="fake-face")
    real = EmbedderSpec(dimensions=128, metric="l2", cutoff=0.6, model="face_recognition-1.3")
    with pytest.raises(EmbedderMismatch, match="fake-face"):
        check_embedders(conn, real, FakeVoiceEmbedder().spec)

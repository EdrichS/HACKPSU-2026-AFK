"""Voice samples. Recording again adds a sample; matching uses each person's best one."""

import psycopg
from psycopg import errors

from contract.setup_api import VoiceSample
from db.errors import NotFound


def add_voice(conn: psycopg.Connection, person_id: int, audio_path: str, embedding: list[float], model: str) -> int:
    try:
        return conn.execute(
            """
            INSERT INTO voice_samples (person_id, audio_path, model, embedding)
            VALUES (%(person_id)s, %(path)s, %(model)s, %(embedding)s::vector)
            RETURNING id
            """,
            {"person_id": person_id, "path": audio_path, "model": model, "embedding": embedding},
        ).fetchone()[0]
    except (errors.ForeignKeyViolation, errors.NumericValueOutOfRange):
        raise NotFound("person") from None


def list_voice(conn: psycopg.Connection, person_id: int) -> list[VoiceSample]:
    rows = conn.execute(
        "SELECT id, created_at FROM voice_samples WHERE person_id = %(person_id)s ORDER BY id",
        {"person_id": person_id},
    )
    return [VoiceSample(voice_sample_id=sid, created_at=created_at) for sid, created_at in rows]


def voice_file(conn: psycopg.Connection, person_id: int, sample_id: int) -> str | None:
    """The recording's path, or None when it isn't this person's."""
    row = conn.execute(
        "SELECT audio_path FROM voice_samples WHERE id = %(sample_id)s AND person_id = %(person_id)s",
        {"sample_id": sample_id, "person_id": person_id},
    ).fetchone()
    return row[0] if row else None


def delete_voice(conn: psycopg.Connection, person_id: int, sample_id: int) -> str | None:
    """Delete one recording; return its file to delete after the commit, or None if not theirs."""
    row = conn.execute(
        "DELETE FROM voice_samples WHERE id = %(sample_id)s AND person_id = %(person_id)s RETURNING audio_path",
        {"sample_id": sample_id, "person_id": person_id},
    ).fetchone()
    return row[0] if row else None

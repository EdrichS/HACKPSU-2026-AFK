"""The people table: each person's name, relationship and card, with their sample counts."""

import psycopg
from psycopg import errors

from contract.setup_api import Person
from db.errors import Conflict

# face_count and has_voice are computed, never stored. COUNT(f.id) skips the NULL row a person
# with no faces gets from the LEFT JOIN; EXISTS keeps faces and voices from multiplying.
_SELECT = """
SELECT p.id, p.name, p.relationship, p.small_context,
       COUNT(f.id) AS face_count,
       EXISTS (SELECT 1 FROM voice_samples v WHERE v.person_id = p.id) AS has_voice
FROM people p
LEFT JOIN face_samples f ON f.person_id = p.id
{where}
GROUP BY p.id
ORDER BY p.name, p.id
"""


def _person(row) -> Person:
    pid, name, relationship, small_context, face_count, has_voice = row
    return Person(
        id=pid,
        name=name,
        relationship=relationship,
        face_count=face_count,
        has_voice=has_voice,
        small_context=small_context,
    )


def list_people(conn: psycopg.Connection) -> list[Person]:
    return [_person(row) for row in conn.execute(_SELECT.format(where=""))]


def get_person(conn: psycopg.Connection, person_id: int) -> Person | None:
    row = conn.execute(_SELECT.format(where="WHERE p.id = %(id)s"), {"id": person_id}).fetchone()
    return _person(row) if row else None


def create_person(conn: psycopg.Connection, name: str, relationship: str) -> Person:
    try:
        pid = conn.execute(
            "INSERT INTO people (name, relationship) VALUES (%(name)s, %(relationship)s) RETURNING id",
            {"name": name, "relationship": relationship},
        ).fetchone()[0]
    except errors.UniqueViolation:
        raise Conflict(f"There's already a {name.strip()}, {relationship.strip()}.") from None
    return get_person(conn, pid)


def update_person(
    conn: psycopg.Connection,
    person_id: int,
    *,
    name: str | None = None,
    relationship: str | None = None,
    small_context: str | None = None,
) -> Person | None:
    """Change the given fields; a field passed as None keeps its value."""
    params = {"id": person_id, "name": name, "relationship": relationship, "small_context": small_context}
    try:
        row = conn.execute(
            """
            UPDATE people
            SET name = COALESCE(%(name)s, name),
                relationship = COALESCE(%(relationship)s, relationship),
                small_context = COALESCE(%(small_context)s, small_context)
            WHERE id = %(id)s
            RETURNING id
            """,
            params,
        ).fetchone()
    except errors.UniqueViolation:
        raise Conflict("Another person already has that name and relationship.") from None
    if row is None:
        return None
    if small_context is not None and small_context.strip():
        # A card the family fixed by hand is also kept as a note, so the next Gemini rewrite
        # starts from their correction.
        conn.execute(
            "INSERT INTO facts (person_id, text, source) VALUES (%(id)s, %(small_context)s, 'notes')"
            " ON CONFLICT DO NOTHING",
            params,
        )
    return get_person(conn, person_id)


def delete_person(conn: psycopg.Connection, person_id: int) -> list[str] | None:
    """Delete the person; return the audio files to delete after the commit, or None if missing.

    The row lock makes any in-flight add_voice or assign_face for this person finish first, and
    later ones fail. The audio paths are read in their own statement after the lock, so they
    include a sample that committed while the lock was being waited for.
    """
    params = {"id": person_id}
    if conn.execute("SELECT id FROM people WHERE id = %(id)s FOR UPDATE", params).fetchone() is None:
        return None
    paths = [path for (path,) in conn.execute(
        "SELECT audio_path FROM voice_samples WHERE person_id = %(id)s ORDER BY id", params
    )]
    # The foreign keys unlabel the person's faces and delete their voice samples and facts.
    conn.execute("DELETE FROM people WHERE id = %(id)s", params)
    return paths

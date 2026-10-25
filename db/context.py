"""The person context: facts (the large context) and the card (people.small_context).

The context owner's routes call these. Their Gemini call happens before save_context, with no
connection held; save_context then writes the card and the new facts in one transaction.
"""

from typing import Literal

import psycopg

from contract.setup_api import Fact, Person
from db.errors import NotFound
from db.people import get_person

LIMIT = 300  # characters, for the card and for each fact


def list_facts(conn: psycopg.Connection, person_id: int) -> list[Fact]:
    """Oldest first, so Gemini can let a newer fact win."""
    rows = conn.execute(
        "SELECT id, text, source, created_at FROM facts WHERE person_id = %(person_id)s ORDER BY created_at, id",
        {"person_id": person_id},
    )
    return [Fact(id=fid, text=text, source=source, created_at=created_at) for fid, text, source, created_at in rows]


def save_context(
    conn: psycopg.Connection,
    person_id: int,
    new_facts: list[str],
    source: Literal["conversation", "notes"],
    small_context: str,
) -> Person:
    """Replace the card and add the new facts. A reply that breaks the limits changes nothing."""
    if len(small_context) > LIMIT:
        raise ValueError(f"The card is {len(small_context)} characters; the limit is {LIMIT}.")
    for fact in new_facts:
        if not fact.strip() or len(fact) > LIMIT:
            raise ValueError(f"Each fact must be 1-{LIMIT} characters and not blank: {fact!r}")
    params = {"person_id": person_id, "small_context": small_context, "source": source}
    if conn.execute(
        "UPDATE people SET small_context = %(small_context)s WHERE id = %(person_id)s RETURNING id", params
    ).fetchone() is None:
        raise NotFound("person")
    for fact in new_facts:
        # Exact repeats (ignoring case and surrounding spaces) are skipped by facts_person_text_key.
        conn.execute(
            "INSERT INTO facts (person_id, text, source) VALUES (%(person_id)s, %(text)s, %(source)s)"
            " ON CONFLICT DO NOTHING",
            {**params, "text": fact},
        )
    return get_person(conn, person_id)


def delete_fact(conn: psycopg.Connection, person_id: int, fact_id: int) -> bool:
    """Delete one fact. The card isn't rewritten: the family edits it, or the next update fixes it."""
    cur = conn.execute(
        "DELETE FROM facts WHERE id = %(fact_id)s AND person_id = %(person_id)s",
        {"fact_id": fact_id, "person_id": person_id},
    )
    return cur.rowcount == 1

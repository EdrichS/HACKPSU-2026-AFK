"""The person context: facts (the large context) and the card (people.small_context).

The context owner's routes call these. Their Claude call happens before save_context, with no
connection held; save_context then writes the card and the new facts in one transaction.
"""

from typing import Literal

import psycopg

import psycopg.errors

from contract.setup_api import Fact, Person
from db.errors import Conflict, NotFound
from db.people import get_person

LIMIT = 300  # characters, for the card and for each fact


def list_facts(conn: psycopg.Connection, person_id: int) -> list[Fact]:
    """Oldest first, so Claude can let a newer fact win."""
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
    if not small_context.strip():
        raise ValueError("The card is blank.")  # the family clears a card with PATCH, not Claude
    if len(small_context) > LIMIT:
        raise ValueError(f"The card is {len(small_context)} characters; the limit is {LIMIT}.")
    _check_facts(new_facts)
    params = {"person_id": person_id, "small_context": small_context, "source": source}
    if conn.execute(
        "UPDATE people SET small_context = %(small_context)s WHERE id = %(person_id)s RETURNING id", params
    ).fetchone() is None:
        raise NotFound("person")
    _insert_facts(conn, person_id, new_facts, source)
    return get_person(conn, person_id)


def add_facts(
    conn: psycopg.Connection,
    person_id: int,
    new_facts: list[str],
    source: Literal["conversation", "notes"],
) -> Person:
    """Add facts and leave the card as it is: for when the card call failed, or there's no card yet."""
    _check_facts(new_facts)
    person = get_person(conn, person_id)
    if person is None:
        raise NotFound("person")
    _insert_facts(conn, person_id, new_facts, source)
    return person


def _check_facts(new_facts: list[str]) -> None:
    for fact in new_facts:
        if not fact.strip() or len(fact) > LIMIT:
            raise ValueError(f"Each fact must be 1-{LIMIT} characters and not blank: {fact!r}")


def _insert_facts(conn: psycopg.Connection, person_id: int, new_facts: list[str], source: str) -> None:
    for fact in new_facts:
        # Exact repeats (ignoring case and surrounding spaces) are skipped by facts_person_text_key.
        conn.execute(
            "INSERT INTO facts (person_id, text, source) VALUES (%(person_id)s, %(text)s, %(source)s)"
            " ON CONFLICT DO NOTHING",
            {"person_id": person_id, "text": fact, "source": source},
        )


def add_fact(conn: psycopg.Connection, person_id: int, text: str, source: Literal["conversation", "notes"] = "notes") -> Fact:
    """One fact typed by the family, as written. Raises Conflict for a repeat, NotFound for no such person."""
    text = " ".join(text.split())
    _check_facts([text])
    if get_person(conn, person_id) is None:
        raise NotFound("person")
    try:
        row = conn.execute(
            "INSERT INTO facts (person_id, text, source) VALUES (%(person_id)s, %(text)s, %(source)s)"
            " RETURNING id, text, source, created_at",
            {"person_id": person_id, "text": text, "source": source},
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise Conflict("That fact is already in the record.") from None
    return Fact(id=row[0], text=row[1], source=row[2], created_at=row[3])


def update_fact(conn: psycopg.Connection, person_id: int, fact_id: int, text: str) -> Fact | None:
    """Reword one fact; None when it isn't this person's. Raises Conflict when the new wording repeats another fact."""
    text = " ".join(text.split())
    _check_facts([text])
    try:
        row = conn.execute(
            "UPDATE facts SET text = %(text)s WHERE id = %(fact_id)s AND person_id = %(person_id)s"
            " RETURNING id, text, source, created_at",
            {"fact_id": fact_id, "person_id": person_id, "text": text},
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise Conflict("Another fact already says that.") from None
    return Fact(id=row[0], text=row[1], source=row[2], created_at=row[3]) if row else None


def delete_fact(conn: psycopg.Connection, person_id: int, fact_id: int) -> bool:
    """Delete one fact. The card isn't rewritten: the family edits it, or the next update fixes it."""
    cur = conn.execute(
        "DELETE FROM facts WHERE id = %(fact_id)s AND person_id = %(person_id)s",
        {"fact_id": fact_id, "person_id": person_id},
    )
    return cur.rowcount == 1

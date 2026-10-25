"""The person-context routes: notes, conversation and facts. backend/app.py mounts this router.

notes and conversation run backend.context_ai.update_context, which calls Claude with no database
connection held and returns the person with their card as stored afterwards.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Request, Response

from backend import context_ai
from contract.setup_api import ConversationIn, Fact, FactIn, NotesIn, Person
from db import context, people
from db.errors import NotFound

router = APIRouter()


@router.post("/people/{person_id}/notes")
def add_notes(request: Request, person_id: int, body: NotesIn) -> Person:
    return context_ai.update_context(request.app.state.pool, person_id, body.text, "notes")


@router.post("/people/{person_id}/conversation")
def add_conversation(request: Request, person_id: int, body: ConversationIn) -> Person:
    return context_ai.update_context(request.app.state.pool, person_id, body.lines, "conversation")


@router.get("/people/{person_id}/facts")
def list_facts(request: Request, person_id: int) -> list[Fact]:
    with request.app.state.pool.connection() as conn:
        if people.get_person(conn, person_id) is None:
            raise NotFound("person")
        return context.list_facts(conn, person_id)


@router.post("/people/{person_id}/facts", status_code=201)
def add_fact(request: Request, person_id: int, body: FactIn) -> Fact:
    """One fact as the family typed it, no Claude: for the management view. 409 for a repeat."""
    with request.app.state.pool.connection() as conn:
        return context.add_fact(conn, person_id, body.text)


@router.patch("/people/{person_id}/facts/{fact_id}")
def update_fact(request: Request, person_id: int, fact_id: int, body: FactIn) -> Fact:
    with request.app.state.pool.connection() as conn:
        fact = context.update_fact(conn, person_id, fact_id, body.text)
    if fact is None:
        raise NotFound("fact")
    return fact


@router.post("/people/{person_id}/card")
def rewrite_card(request: Request, person_id: int) -> Person:
    """Write the card again from the stored facts (after the family added, reworded or deleted some).

    503 without a Claude key; 502 when Claude gives no usable card, leaving the old one.
    """
    with request.app.state.pool.connection() as conn:
        person = people.get_person(conn, person_id)
        if person is None:
            raise NotFound("person")
        facts = context.list_facts(conn, person_id)
    if not facts:
        raise HTTPException(422, "There are no facts to write a card from.")
    try:
        client = context_ai.get_client()
    except Exception as e:  # noqa: BLE001  (no key, or no SDK)
        raise HTTPException(503, f"Cards need Claude: {e}") from None
    card = context_ai.write_card(client, person, facts, [], "notes", date.today())
    if card is None:
        raise HTTPException(502, "Claude could not write the card; the old one is kept.")
    with request.app.state.pool.connection() as conn:
        return context.save_context(conn, person_id, [], "notes", card)


@router.delete("/people/{person_id}/facts/{fact_id}", status_code=204)
def delete_fact(request: Request, person_id: int, fact_id: int) -> Response:
    with request.app.state.pool.connection() as conn:
        if not context.delete_fact(conn, person_id, fact_id):
            raise NotFound("fact")
    return Response(status_code=204)

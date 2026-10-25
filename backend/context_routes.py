"""The person-context routes: notes, conversation and facts. backend/app.py mounts this router.

notes and conversation run backend.gemini.update_context, which calls Gemini with no database
connection held and returns the person with their card as stored afterwards.
"""

from fastapi import APIRouter, Request, Response

from backend import gemini
from contract.setup_api import ConversationIn, Fact, NotesIn, Person
from db import context, people
from db.errors import NotFound

router = APIRouter()


@router.post("/people/{person_id}/notes")
def add_notes(request: Request, person_id: int, body: NotesIn) -> Person:
    return gemini.update_context(request.app.state.pool, person_id, body.text, "notes")


@router.post("/people/{person_id}/conversation")
def add_conversation(request: Request, person_id: int, body: ConversationIn) -> Person:
    return gemini.update_context(request.app.state.pool, person_id, body.lines, "conversation")


@router.get("/people/{person_id}/facts")
def list_facts(request: Request, person_id: int) -> list[Fact]:
    with request.app.state.pool.connection() as conn:
        if people.get_person(conn, person_id) is None:
            raise NotFound("person")
        return context.list_facts(conn, person_id)


@router.delete("/people/{person_id}/facts/{fact_id}", status_code=204)
def delete_fact(request: Request, person_id: int, fact_id: int) -> Response:
    with request.app.state.pool.connection() as conn:
        if not context.delete_fact(conn, person_id, fact_id):
            raise NotFound("fact")
    return Response(status_code=204)

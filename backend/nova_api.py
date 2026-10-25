"""Nova over HTTP: ask a question, get the sentence to speak. The database is her only source."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from enroll import store
from live.nova import NovaBrain
from live.presence import Presence

router = APIRouter(prefix="/nova", tags=["nova"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    asker: str | None = None  # who is asking, if known; the user otherwise


class AskOut(BaseModel):
    text: str


@router.post("/ask")
def ask(request: Request, body: AskIn) -> AskOut:
    state = request.app.state
    if state.claude is None:
        raise HTTPException(503, "Nova is off: no ANTHROPIC_API_KEY.")
    with state.pool.connection() as conn:
        user = store.find_user(conn)
    presence = state.presence if state.presence is not None else Presence()
    # Each request stands alone, so an introduction would open every answer.
    brain = NovaBrain(state.claude, state.pool, presence, "Nova", user.name if user else "the user", introduce=False)
    return AskOut(text=brain.answer(body.question, body.asker))

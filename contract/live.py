"""Messages on the /live WebSocket, in both directions, and the sentences the app speaks.

The backend composes every spoken sentence; the frontend speaks `text` exactly as received.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from contract.embedders import Box

UNKNOWN_TEXT = "I don't recognize this person."
EMPTY_ROOM_TEXT = "I don't see anyone I know right now."


# From the client. The frontend sends no audio while the app is speaking; that mutes the mic.

class Frame(BaseModel):
    type: Literal["frame"] = "frame"
    ts: int  # milliseconds since the epoch
    jpeg: str  # base64


class Audio(BaseModel):
    type: Literal["audio"] = "audio"
    ts: int
    wav: str  # base64; 16 kHz mono WAV


class Who(BaseModel):
    type: Literal["who"] = "who"


ClientMessage = Annotated[Frame | Audio | Who, Field(discriminator="type")]


# From the server.

class PresentPerson(BaseModel):
    person_id: int
    name: str
    relationship: str
    small_context: str


class TrackedFace(BaseModel):
    box: Box
    state: Literal["named", "unsure", "unknown"]
    person_id: int | None


class Present(BaseModel):
    """Sent after every frame, for the on-screen labels."""

    type: Literal["present"] = "present"
    people: list[PresentPerson]
    faces: list[TrackedFace]


class Arrived(BaseModel):
    type: Literal["arrived"] = "arrived"
    person: PresentPerson
    via: Literal["face", "voice"]
    text: str


class Unknown(BaseModel):
    type: Literal["unknown"] = "unknown"
    text: str = UNKNOWN_TEXT


class WhoAnswer(BaseModel):
    type: Literal["who_answer"] = "who_answer"
    text: str


class Error(BaseModel):
    type: Literal["error"] = "error"
    message: str


ServerMessage = Annotated[Present | Arrived | Unknown | WhoAnswer | Error, Field(discriminator="type")]

_client_messages = TypeAdapter(ClientMessage)


def parse_client(raw: str) -> Frame | Audio | Who:
    """Parse one client message; raises pydantic.ValidationError for anything else."""
    return _client_messages.validate_json(raw)


def who_text(people: list[PresentPerson]) -> str:
    """The spoken sentence naming everyone present, e.g. "That's David, your grandson."

    With one person this is also the arrival sentence. The backend calls this, never rewrites it.
    """
    if not people:
        return EMPTY_ROOM_TEXT
    items = [f"{p.name}, your {p.relationship}" for p in people]
    body = items[0] if len(items) == 1 else ", ".join(items[:-1]) + ", and " + items[-1]
    return f"That's {body}."

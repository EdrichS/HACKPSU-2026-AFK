"""Messages on the /live WebSocket, in both directions, and the sentences the app speaks.

The backend composes every spoken sentence; the frontend speaks `text` exactly as received.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from contract.embedders import Box

UNKNOWN_TEXT = "I don't recognize this person."
EMPTY_ROOM_TEXT = "I don't see anyone I know right now."
UNKNOWN_SPEAKER = "Someone"  # a voice that matches nobody in the transcript; captions carry null instead


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


class EndVisit(BaseModel):
    """The visit is over: summarize it into each visitor's facts and card."""

    type: Literal["end_visit"] = "end_visit"


ClientMessage = Annotated[Frame | Audio | Who | EndVisit, Field(discriminator="type")]


# From the server.

class PresentPerson(BaseModel):
    person_id: int
    name: str
    relationship: str
    small_context: str
    facts: list[str] = []  # the newest few facts, for the bullets beside the name


class TrackedFace(BaseModel):
    box: Box
    state: Literal["named", "unsure", "unknown"]
    person_id: int | None


class Present(BaseModel):
    """Sent after every frame that decodes, for the on-screen labels."""

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


class Caption(BaseModel):
    """An utterance, transcribed, with who said it. Live captions on screen.

    Only a voice that matches someone in voice_samples gets a name and an id, the user's own
    voice included; any other voice has speaker and person_id None. With cloud captions a
    sentence arrives while it is being said (`final` false, each caption replacing the last) and
    then once more finished.
    """

    type: Literal["caption"] = "caption"
    person_id: int | None
    speaker: str | None
    text: str
    final: bool = True  # False: still being said; local captions send finished sentences only
    start: float  # seconds of audio since the connection opened
    end: float


class Answer(BaseModel):
    """Nova's reply to a question heard after the wake word; the frontend speaks `text`."""

    type: Literal["answer"] = "answer"
    question: str
    text: str


class VisitSaved(BaseModel):
    """After end_visit: what was learned about one visitor and their new card."""

    type: Literal["visit_saved"] = "visit_saved"
    person_id: int
    name: str
    new_facts: list[str]
    small_context: str


class Error(BaseModel):
    type: Literal["error"] = "error"
    message: str


ServerMessage = Annotated[
    Present | Arrived | Unknown | WhoAnswer | Caption | Answer | VisitSaved | Error, Field(discriminator="type")
]

_client_messages = TypeAdapter(ClientMessage)


def parse_client(raw: str) -> Frame | Audio | Who | EndVisit:
    """Parse one client message; raises pydantic.ValidationError for anything else."""
    return _client_messages.validate_json(raw)  # type: ignore[return-value]


def who_text(people: list[PresentPerson]) -> str:
    """The spoken answer to "Who is this?", naming everyone present, e.g. "That's David, your grandson."

    Arrivals use arrival_text instead. The backend calls this, never rewrites it.
    """
    if not people:
        return EMPTY_ROOM_TEXT
    items = [f"{p.name}, your {p.relationship}" for p in people]
    body = items[0] if len(items) == 1 else ", ".join(items[:-1]) + ", and " + items[-1]
    return f"That's {body}."


def arrival_text(person: PresentPerson) -> str:
    """The spoken sentence for someone arriving, e.g. "Here's David, your grandson.": an introduction,
    where "That's …" unasked can sound like correcting the wearer. The backend calls this, never rewrites it."""
    return f"Here's {person.name}, your {person.relationship}."

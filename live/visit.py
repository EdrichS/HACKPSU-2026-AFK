"""The visit: a speaker-labelled transcript that Claude turns into facts and a fresh card.

Follows the design's person-context rules (docs/superpowers/specs, "Person context"): one call
per visit per visitor; facts are only ever added; the card is rewritten from all the facts; a
failed call or bad JSON changes nothing. Rows go through db.context.save_context, so facts get
source 'conversation' and people.small_context gets the card.
"""

import logging
import time
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from contract.live import PresentPerson
from contract.setup_api import Person, TranscriptLine
from db import context, people

log = logging.getLogger("live.visit")

MODEL = "claude-opus-5-5"
LIMIT = context.LIMIT  # 300 characters: the card, and each fact

SYSTEM = f"""You maintain what a memory-care app knows about the people in a patient's life. The patient has \
dementia. After each visit you read the speaker-labelled transcript and update one visitor's record. \
You answer with JSON that has two fields.

new_facts: short facts about the visitor and their life learned in this conversation, one per string, \
each under {LIMIT} characters. Only facts about the visitor, never about the patient. Skip anything \
already in the existing facts, even if worded differently: conversations with someone with dementia \
repeat a lot. When a new fact replaces an old one (they moved, changed jobs), state the new one. \
An empty list is a fine answer.

small_context: the visitor's card, rewritten from all the facts, old and new. At most two short \
sentences in plain words, under {LIMIT} characters, that help the patient place this person, like \
"David is your grandson. He just moved to Pittsburgh and works as a nurse." Where facts conflict, the \
newer wins. Never put deaths, illness, diagnoses or bad news on the card. If nothing new was learned, \
return the existing card unchanged; if there is no card yet, write one from the existing facts and \
the relationship."""

SCHEMA = {
    "type": "object",
    "properties": {
        "new_facts": {"type": "array", "items": {"type": "string"}},
        "small_context": {"type": "string"},
    },
    "required": ["new_facts", "small_context"],
    "additionalProperties": False,
}


class VisitSummary(BaseModel):
    new_facts: list[str] = Field(default_factory=list)
    small_context: str = ""


@dataclass
class Line:
    t: float
    speaker: str
    person_id: int | None
    text: str


@dataclass
class Visit:
    started: float = field(default_factory=time.time)
    lines: list[Line] = field(default_factory=list)
    people: dict[int, PresentPerson] = field(default_factory=dict)  # known people seen, by id

    @property
    def last_line(self) -> float:
        return self.lines[-1].t if self.lines else self.started

    def add(self, speaker: str, person_id: int | None, text: str) -> Line | None:
        text = text.strip()
        if not text:
            return None
        line = Line(time.time(), speaker, person_id, text)
        self.lines.append(line)
        return line

    def note(self, person: PresentPerson) -> None:
        self.people[person.person_id] = person

    def transcript(self) -> list[TranscriptLine]:
        return [TranscriptLine(speaker=line.speaker, text=line.text) for line in self.lines]


def render_transcript(lines: list[Line]) -> str:
    return "\n".join(f"{line.speaker}: {line.text}" for line in lines)


def summarize(client, person: Person, existing_facts: list[str], lines: list[Line], user_name: str, model: str = MODEL) -> VisitSummary | None:
    """One Claude call for one visitor. Returns None, and logs why, when the result can't be used."""
    facts = "\n".join(f"- {f}" for f in existing_facts) or "(none yet)"
    prompt = (
        f"Visitor: {person.name}, the patient's {person.relationship}.\n"
        f"The patient, the app's user wearing the glasses, is {user_name}.\n"
        f"Existing card: {person.small_context or '(none)'}\n"
        f"Existing facts:\n{facts}\n\n"
        f"Transcript of the visit:\n{render_transcript(lines)}"
    )
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=1500,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
    except Exception as e:  # noqa: BLE001  (any API failure: keep the old card)
        log.error("summary for %s failed: %s: %s", person.name, type(e).__name__, e)
        return None
    if response.stop_reason == "refusal":
        log.error("summary for %s refused: %s", person.name, getattr(response, "stop_details", None))
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return VisitSummary.model_validate_json(text)
    except ValidationError as e:
        log.error("summary for %s was not the expected JSON: %s", person.name, e)
        return None


def fit_card(card: str, limit: int = LIMIT) -> str:
    """The card within the limit, cut at a sentence end if there is one, else at a space."""
    card = " ".join(card.split())
    if len(card) <= limit:
        return card
    head = card[:limit]
    for mark in (". ", "! ", "? "):
        cut = head.rfind(mark)
        if cut > 0:
            return head[: cut + 1]
    return head.rsplit(" ", 1)[0]


@dataclass
class VisitResult:
    person: PresentPerson
    summary: VisitSummary | None
    updated: Person | None  # the row after saving, or None when nothing was stored


def save_visit(pool, client, visit: Visit, user_name: str, user_id: int | None = None, model: str = MODEL) -> list[VisitResult]:
    """Summarize the visit once per known person who was there, and store each result."""
    results = []
    for pid, present in visit.people.items():
        if pid == user_id:
            continue  # never "facts" about the user themselves
        with pool.connection() as conn:
            row = people.get_person(conn, pid)
            existing = [f.text for f in context.list_facts(conn, pid)] if row else []
        if row is None:
            continue
        summary = summarize(client, row, existing, visit.lines, user_name, model) if client else None
        if summary is None:
            results.append(VisitResult(present, None, None))
            continue
        card = fit_card(summary.small_context) or row.small_context
        new_facts = [fit_card(f) for f in summary.new_facts if f.strip()]
        if not card:
            log.warning("no card for %s yet; nothing to store", row.name)
            results.append(VisitResult(present, summary, None))
            continue
        try:
            with pool.connection() as conn:
                updated = context.save_context(conn, pid, new_facts, "conversation", card)
        except ValueError as e:
            log.error("could not store the summary for %s: %s", row.name, e)
            results.append(VisitResult(present, summary, None))
            continue
        results.append(VisitResult(present, summary, updated))
    return results

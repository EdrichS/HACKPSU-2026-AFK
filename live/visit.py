"""The visit: a speaker-labelled transcript, and what happens to it when the visit ends.

The summary itself belongs to the context owner: backend.gemini.update_context turns the
transcript into new facts (source 'conversation') and a fresh card with two Gemini calls, holding
no database connection meanwhile, and leaves everything as it was when a call fails. This module
keeps the transcript and reports what that call changed.
"""

import logging
import time
from dataclasses import dataclass, field

from contract.live import PresentPerson
from contract.setup_api import Person, TranscriptLine
from db import context, people
from db.errors import NotFound

log = logging.getLogger("live.visit")


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


@dataclass
class VisitResult:
    person: PresentPerson
    new_facts: list[str]
    updated: Person | None  # the row afterwards, or None when nothing changed (Gemini off, failed, or nothing new)


def save_visit(pool, visit: Visit, user_id: int | None = None, client=None, today=None) -> list[VisitResult]:
    """Hand the whole transcript to backend.gemini.update_context once per visitor who was there.

    The user (the wearer) is never a visitor. `client` and `today` are for tests.
    """
    from backend import gemini

    results = []
    for pid, present in visit.people.items():
        if pid == user_id:
            continue
        with pool.connection() as conn:
            row = people.get_person(conn, pid)
            before = {f.id for f in context.list_facts(conn, pid)}
        if row is None:
            continue
        try:
            person = gemini.update_context(pool, pid, visit.transcript(), "conversation", client=client, today=today)
        except NotFound:
            continue
        with pool.connection() as conn:
            new_facts = [f.text for f in context.list_facts(conn, pid) if f.id not in before]
        changed = bool(new_facts) or person.small_context != row.small_context
        results.append(VisitResult(present, new_facts, person if changed else None))
    return results

"""Person context with Gemini: new text -> new facts -> a fresh card.

Two calls, each with its own prompt, because the two jobs have different scopes:

- The facts call reads the new text (typed notes, or a visit's speaker-labelled transcript) and
  returns the facts it adds. Facts are a neutral record: good news and bad, past and upcoming
  events, interests. They are only ever added.
- The card call reads the stored facts plus the new ones (never the raw text) and writes the card:
  at most CARD_LIMIT characters, recent, upbeat, with things to ask about. No bad news.

update_context runs the flow for one person, holding no database connection while Gemini works.
A failed facts call changes nothing. A failed card call still stores the facts and keeps the old card.
"""

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

from contract.setup_api import Fact, Person, TranscriptLine
from db import context, people
from db.errors import NotFound

log = logging.getLogger("backend.gemini")

ROOT = Path(__file__).resolve().parents[1]
# Newest stable Flash model as of 2026-10-24 (https://ai.google.dev/gemini-api/docs/models).
DEFAULT_MODEL = "gemini-3.8-flash"
THINKING_LEVEL = "low"  # 3.8 Flash takes low, medium (its default) or high; low keeps "End visit" quick
CARD_LIMIT = 200  # characters; the database allows 300, the card is kept shorter to read at a glance
FACT_LIMIT = context.LIMIT  # 300 characters, the database's limit

FACTS_PROMPT = f"""\
You keep the record of one person in the life of a patient with dementia. You read new text about
that person and return, as JSON, the facts it adds to their record.

The new text is either notes typed into a form (by the person themselves, often in the first
person, or by a family member) or a speaker-labelled transcript of a visit with the patient.

What counts as a fact:
- Their life: home, work, school, family, partner, pets, health, what they own or just bought.
- Their interests: hobbies, what they love to talk about.
- Events, past or upcoming: birthdays, graduations, weddings, funerals, trips, moves, gatherings.
- Good and bad news alike. The record is neutral: a death, an illness or a breakup is stored like
  any other fact. A separate step decides what is shown to the patient.

Rules:
1. Only facts about this person. Never facts about the patient, even when the patient talks
   about themselves.
2. Only what the text states. A question or a guess is not a fact ("Are you still in
   Philadelphia?" is not). Never invent anything.
3. Skip anything already in the stored facts, even when worded differently. Conversations with
   someone with dementia repeat a lot. If nothing is new, return an empty list.
4. When something has changed (they moved, changed jobs, an event happened), add the new state as
   a new fact. Never restate or correct an old fact.
5. Turn relative dates into real ones using today's date: "next month", said on 2026-10-24,
   becomes "November 2026". Keep exact dates when given.
6. Each fact is one short standalone sentence starting with the person's name, under {FACT_LIMIT}
   characters. Never use he, she, him, his or her: "David bought a Tesla in October 2026".
"""

CARD_PROMPT = f"""\
You write the card a patient with dementia sees when someone they know is recognized. It helps the
patient start a happy conversation. The person's name is shown next to the card, so never write it.

You get the person's stored facts with the date each was recorded, oldest first, and the facts
that were just added. Return the card as JSON.

Format:
Last spoke about: <topic> · <fact> · <fact> | Ask about: <topic>, <topic>
Example:
Last spoke about: graduating in Nov · Works in software · Loves cars | Ask about: the new Tesla, graduation plans

Rules:
1. At most {CARD_LIMIT} characters in total. Short fragments, not sentences. No pronouns (he, she,
   his, her) and no name.
2. "Last spoke about" is the main topic of the latest conversation. Use it only when the new facts
   came from a conversation; otherwise leave that part out and start with the facts.
3. The middle items are the most useful current facts: where they live, what they do, what they
   love. Newer facts win over older ones.
4. "Ask about" is one or two warm, easy conversation starters: an upcoming event, something new,
   a hobby.
5. Never put death, funerals, illness, injury, surgery, diagnoses, breakups, job loss, money
   trouble or other bad news on the card, and never suggest asking about them. If a later fact
   ends or spoils an earlier one (a pet died, a job ended), leave both out.
6. Use only the facts. Never invent anything, and nothing about the patient.
7. Use today's date: an event whose date has passed is not upcoming. Call it past ("just
   graduated") or leave it out.
"""

FACTS_SCHEMA = {
    "type": "object",
    "properties": {"new_facts": {"type": "array", "items": {"type": "string"}}},
    "required": ["new_facts"],
}
CARD_SCHEMA = {
    "type": "object",
    "properties": {"small_context": {"type": "string"}},
    "required": ["small_context"],
}

Source = Literal["conversation", "notes"]
Text = str | list[TranscriptLine]


def load_env() -> None:
    """GEMINI_API_KEY (and GEMINI_MODEL) from the repo's gitignored .env, never overriding real env vars."""
    load_dotenv(ROOT / ".env")


def make_client():
    from google import genai
    from google.genai import types

    load_env()
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is not set; put it in the repo's .env")
    # Flash answers 503 "high demand" now and then; retry a few times before giving up.
    retry = types.HttpRetryOptions(attempts=4, initial_delay=1.0, max_delay=8.0, http_status_codes=[429, 500, 503, 504])
    return genai.Client(http_options=types.HttpOptions(retry_options=retry))  # reads GEMINI_API_KEY


_client = None


def get_client():
    """One client for the whole process, made on first use."""
    global _client
    if _client is None:
        _client = make_client()
    return _client


def format_text(text: Text) -> str:
    """Notes pass through; a transcript becomes `Speaker: text` lines."""
    if isinstance(text, str):
        return text.strip()
    lines = []
    for line in text:
        speaker, said = (line["speaker"], line["text"]) if isinstance(line, dict) else (line.speaker, line.text)
        if said.strip():
            lines.append(f"{speaker}: {said.strip()}")
    return "\n".join(lines)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "(none yet)"


def facts_request(person: Person, existing: list[Fact], text: Text, today: date, patient: str | None = None) -> str:
    kind = "Typed notes" if isinstance(text, str) else "Transcript of the visit"
    who = f"The patient is {patient}; lines from {patient} or from 'Patient' are the patient.\n" if patient else ""
    return (
        f"Today: {today.isoformat()}\n"
        f"Person: {person.name}, the patient's {person.relationship}\n"
        f"{who}\n"
        f"Stored facts:\n{_bullets([f.text for f in existing])}\n\n"
        f"{kind}:\n{format_text(text)}\n"
    )


def card_request(person: Person, existing: list[Fact], new_facts: list[str], source: Source, today: date) -> str:
    stored = [f"{f.created_at.date().isoformat()}: {f.text}" for f in existing]
    just_added = "from the latest conversation" if source == "conversation" else "from typed notes, not a conversation"
    return (
        f"Today: {today.isoformat()}\n"
        f"Person: {person.name}, the patient's {person.relationship}\n\n"
        f"Stored facts, oldest first:\n{_bullets(stored)}\n\n"
        f"Just added, {just_added}:\n{_bullets(new_facts)}\n"
    )


def _ask(client, system: str, contents: str, schema: dict) -> dict:
    from google.genai import types

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
        ),
    )
    data = json.loads(response.text)
    if not isinstance(data, dict):
        raise ValueError("the reply is not a JSON object")
    return data


def extract_facts(client, person: Person, existing: list[Fact], text: Text, today: date, patient: str | None = None) -> list[str] | None:
    """The facts call. New facts, cleaned; None (and a log line) when the call or its reply fails."""
    try:
        facts = _ask(client, FACTS_PROMPT, facts_request(person, existing, text, today, patient), FACTS_SCHEMA).get("new_facts")
        if not isinstance(facts, list) or not all(isinstance(f, str) for f in facts):
            raise ValueError("new_facts is not a list of strings")
    except Exception as e:  # noqa: BLE001  (any failure: change nothing)
        log.error("facts call for %s failed: %s: %s", person.name, type(e).__name__, e)
        return None
    seen = {f.text.strip().casefold() for f in existing}
    fresh = []
    for fact in (" ".join(f.split()) for f in facts):
        if not fact or fact.casefold() in seen:
            continue
        if len(fact) > FACT_LIMIT:
            log.warning("dropping a %d-character fact for %s", len(fact), person.name)
            continue
        seen.add(fact.casefold())
        fresh.append(fact)
    return fresh


def write_card(client, person: Person, existing: list[Fact], new_facts: list[str], source: Source, today: date) -> str | None:
    """The card call. The new card; None (and a log line) when the call fails or the card breaks the limit."""
    try:
        card = _ask(client, CARD_PROMPT, card_request(person, existing, new_facts, source, today), CARD_SCHEMA).get("small_context")
        if not isinstance(card, str):
            raise ValueError("small_context is not a string")
        card = " ".join(card.split())
        if not card:
            raise ValueError("the card is blank")
        if len(card) > CARD_LIMIT:
            raise ValueError(f"the card is {len(card)} characters; the limit is {CARD_LIMIT}")
    except Exception as e:  # noqa: BLE001  (any failure: keep the old card)
        log.error("card call for %s failed: %s: %s", person.name, type(e).__name__, e)
        return None
    return card


def _patient_name(conn) -> str | None:
    """The app's user (the patient), registered with the relationship 'user'."""
    return next((p.name for p in people.list_people(conn) if p.relationship == "user"), None)


def update_context(pool: ConnectionPool, person_id: int, text: Text, source: Source, client=None, today: date | None = None) -> Person:
    """New text about one person -> new facts -> a fresh card. Returns the person as stored afterwards.

    Raises NotFound for an unknown person. Every Gemini failure is logged and leaves the old card.
    """
    today = today or date.today()
    with pool.connection() as conn:
        person = people.get_person(conn, person_id)
        if person is None:
            raise NotFound("person")
        existing = context.list_facts(conn, person_id)
        patient = _patient_name(conn)
    if not format_text(text):
        return person

    try:
        client = client or get_client()
    except Exception as e:  # noqa: BLE001  (no key, or no SDK: the app keeps working without Gemini)
        log.error("no Gemini client, %s's context is unchanged: %s", person.name, e)
        return person

    new_facts = extract_facts(client, person, existing, text, today, patient)
    if new_facts is None:
        return person
    card = None
    if new_facts or (existing and not person.small_context):  # a repeat visit keeps the card as it is
        card = write_card(client, person, existing, new_facts, source, today)
    if not new_facts and card is None:
        return person

    with pool.connection() as conn:
        if card:
            return context.save_context(conn, person_id, new_facts, source, card)
        return context.add_facts(conn, person_id, new_facts, source)

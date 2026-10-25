"""backend.gemini without a database or the network (one live test, skipped without a key)."""

import os
from datetime import date, datetime, timezone

import pytest

from backend import gemini
from contract.setup_api import Fact, Person, TranscriptLine
from tests.gemini_fakes import FakeGemini

TODAY = date(2026, 10, 24)
DAVID = Person(id=1, name="David", relationship="grandson", face_count=0, has_voice=False, small_context="")
STORED = [Fact(id=1, text="David lives in Philadelphia.", source="notes", created_at=datetime(2026, 9, 1, tzinfo=timezone.utc))]
LINES = [TranscriptLine(speaker="Rose", text="Did you move?"), TranscriptLine(speaker="David", text="Yeah, last month.")]


def test_transcript_becomes_labelled_lines():
    assert gemini.format_text(LINES) == "Rose: Did you move?\nDavid: Yeah, last month."
    assert gemini.format_text([{"speaker": "David", "text": " Hi "}, {"speaker": "Rose", "text": " "}]) == "David: Hi"
    assert gemini.format_text("  I just bought a Tesla.  ") == "I just bought a Tesla."


def test_facts_request_has_today_the_patient_and_the_stored_facts():
    text = gemini.facts_request(DAVID, STORED, LINES, TODAY, patient="Rose")
    assert "Today: 2026-10-24" in text
    assert "David, the patient's grandson" in text
    assert "lines from Rose or from 'Patient' are the patient" in text
    assert "- David lives in Philadelphia." in text
    assert "Transcript of the visit:\nRose: Did you move?" in text
    assert "Typed notes:" in gemini.facts_request(DAVID, [], "I'm a nurse.", TODAY)


def test_card_request_dates_the_stored_facts_and_marks_the_new_ones():
    text = gemini.card_request(DAVID, STORED, ["David moved to Pittsburgh in September 2026."], "conversation", TODAY)
    assert "- 2026-09-01: David lives in Philadelphia." in text
    assert "Just added, from the latest conversation:\n- David moved to Pittsburgh" in text
    assert "not a conversation" in gemini.card_request(DAVID, [], ["x"], "notes", TODAY)


def test_both_calls_ask_for_json_with_their_own_prompt_and_low_thinking():
    fake = FakeGemini(facts={"new_facts": ["David moved to Pittsburgh."]}, card={"small_context": "Lives in Pittsburgh"})
    gemini.extract_facts(fake, DAVID, STORED, LINES, TODAY)
    gemini.write_card(fake, DAVID, STORED, ["David moved to Pittsburgh."], "conversation", TODAY)
    (_, facts_call), (_, card_call) = fake.calls
    for call in (facts_call, card_call):
        assert call["config"].response_mime_type == "application/json"
        assert call["config"].thinking_config.thinking_level.value == "LOW"
    assert facts_call["config"].system_instruction == gemini.FACTS_PROMPT
    assert card_call["config"].system_instruction == gemini.CARD_PROMPT
    assert set(card_call["config"].response_json_schema["properties"]) == {"small_context"}


def test_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    fake = FakeGemini()
    gemini.extract_facts(fake, DAVID, [], "notes", TODAY)
    assert fake.calls[0][1]["model"] == "gemini-test"


def test_new_facts_are_cleaned():
    reply = {"new_facts": ["  david lives in philadelphia. ", "David is a nurse.", "David is a nurse.", "  ", "x" * 301]}
    assert gemini.extract_facts(FakeGemini(facts=reply), DAVID, STORED, LINES, TODAY) == ["David is a nurse."]


@pytest.mark.parametrize(
    "reply",
    [RuntimeError("network down"), "not json", None, ["a list"], {"new_facts": "one fact"}, {"new_facts": [1, 2]}],
    ids=["error", "bad-json", "no-text", "not-object", "not-list", "not-strings"],
)
def test_a_failed_facts_call_returns_none(reply):
    assert gemini.extract_facts(FakeGemini(facts=reply), DAVID, STORED, LINES, TODAY) is None


def test_card_is_tidied():
    fake = FakeGemini(card={"small_context": "  Lives in Pittsburgh ·\n Works as a nurse  "})
    assert gemini.write_card(fake, DAVID, [], ["x"], "notes", TODAY) == "Lives in Pittsburgh · Works as a nurse"


@pytest.mark.parametrize(
    "reply",
    [RuntimeError("quota"), "not json", {"small_context": "   "}, {"small_context": "x" * 201}, {"small_context": 5}],
    ids=["error", "bad-json", "blank", "too-long", "not-string"],
)
def test_a_bad_card_returns_none(reply):
    assert gemini.write_card(FakeGemini(card=reply), DAVID, [], ["x"], "notes", TODAY) is None


def test_card_at_the_limit_is_kept():
    card = "x" * gemini.CARD_LIMIT
    assert gemini.write_card(FakeGemini(card={"small_context": card}), DAVID, [], ["x"], "notes", TODAY) == card


gemini.load_env()


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
def test_live_gemini_facts_then_card():
    client = gemini.make_client()
    lines = LINES + [TranscriptLine(speaker="David", text="I moved to Pittsburgh. I'm a nurse at UPMC now.")]
    facts = gemini.extract_facts(client, DAVID, STORED, lines, TODAY, patient="Rose")
    assert facts
    card = gemini.write_card(client, DAVID, STORED, facts, "conversation", TODAY)
    assert card and len(card) <= gemini.CARD_LIMIT
    assert "David" not in card

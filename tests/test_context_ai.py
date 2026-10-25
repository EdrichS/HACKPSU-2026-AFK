"""backend.context_ai without a database or the network (one live test, skipped without a key)."""

import os
from datetime import date, datetime, timezone

import pytest

from backend import context_ai
from contract.setup_api import Fact, Person, TranscriptLine
from tests.claude_fakes import FakeClaude

TODAY = date(2026, 10, 24)
DAVID = Person(id=1, name="David", relationship="grandson", face_count=0, has_voice=False, small_context="")
STORED = [Fact(id=1, text="David lives in Philadelphia.", source="notes", created_at=datetime(2026, 9, 1, tzinfo=timezone.utc))]
LINES = [TranscriptLine(speaker="Rose", text="Did you move?"), TranscriptLine(speaker="David", text="Yeah, last month.")]


def test_transcript_becomes_labelled_lines():
    assert context_ai.format_text(LINES) == "Rose: Did you move?\nDavid: Yeah, last month."
    assert context_ai.format_text([{"speaker": "David", "text": " Hi "}, {"speaker": "Rose", "text": " "}]) == "David: Hi"
    assert context_ai.format_text("  I just bought a Tesla.  ") == "I just bought a Tesla."


def test_facts_request_has_today_the_patient_and_the_stored_facts():
    text = context_ai.facts_request(DAVID, STORED, LINES, TODAY, patient="Rose")
    assert "Today: 2026-10-24" in text
    assert "David, the patient's grandson" in text
    assert "lines from Rose or from 'Patient' are the patient" in text
    assert "- David lives in Philadelphia." in text
    assert "Transcript of the visit:\nRose: Did you move?" in text
    assert "Typed notes:" in context_ai.facts_request(DAVID, [], "I'm a nurse.", TODAY)


def test_card_request_dates_the_stored_facts_and_marks_the_new_ones():
    text = context_ai.card_request(DAVID, STORED, ["David moved to Pittsburgh in September 2026."], "conversation", TODAY)
    assert "- 2026-09-01: David lives in Philadelphia." in text
    assert "Just added, from the latest conversation:\n- David moved to Pittsburgh" in text
    assert "not a conversation" in context_ai.card_request(DAVID, [], ["x"], "notes", TODAY)


def test_both_calls_ask_for_json_of_their_own_shape_with_their_own_prompt():
    fake = FakeClaude(facts={"new_facts": ["David moved to Pittsburgh."]}, card={"small_context": "Lives in Pittsburgh"})
    context_ai.extract_facts(fake, DAVID, STORED, LINES, TODAY)
    context_ai.write_card(fake, DAVID, STORED, ["David moved to Pittsburgh."], "conversation", TODAY)
    (_, facts_call), (_, card_call) = fake.calls
    for call in (facts_call, card_call):
        assert call["output_config"]["format"]["type"] == "json_schema"  # structured output: always that shape
        assert call["output_config"]["format"]["schema"]["additionalProperties"] is False
        assert call["messages"][0]["role"] == "user"
    assert facts_call["system"] == context_ai.FACTS_PROMPT
    assert card_call["system"] == context_ai.CARD_PROMPT
    assert set(card_call["output_config"]["format"]["schema"]["properties"]) == {"small_context"}


def test_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CONTEXT_MODEL", "claude-test")
    fake = FakeClaude()
    context_ai.extract_facts(fake, DAVID, [], "notes", TODAY)
    assert fake.calls[0][1]["model"] == "claude-test"


def test_new_facts_are_cleaned():
    reply = {"new_facts": ["  david lives in philadelphia. ", "David is a nurse.", "David is a nurse.", "  ", "x" * 301]}
    assert context_ai.extract_facts(FakeClaude(facts=reply), DAVID, STORED, LINES, TODAY) == ["David is a nurse."]


@pytest.mark.parametrize(
    "reply",
    [RuntimeError("network down"), "not json", None, ["a list"], {"new_facts": "one fact"}, {"new_facts": [1, 2]}],
    ids=["error", "bad-json", "no-text", "not-object", "not-list", "not-strings"],
)
def test_a_failed_facts_call_returns_none(reply):
    assert context_ai.extract_facts(FakeClaude(facts=reply), DAVID, STORED, LINES, TODAY) is None


def test_card_is_tidied():
    fake = FakeClaude(card={"small_context": "  Lives in Pittsburgh ·\n Works as a nurse  "})
    assert context_ai.write_card(fake, DAVID, [], ["x"], "notes", TODAY) == "Lives in Pittsburgh · Works as a nurse"


@pytest.mark.parametrize(
    "reply",
    [RuntimeError("quota"), "not json", {"small_context": "   "}, {"small_context": "x" * 201}, {"small_context": 5}],
    ids=["error", "bad-json", "blank", "too-long", "not-string"],
)
def test_a_bad_card_returns_none(reply):
    assert context_ai.write_card(FakeClaude(card=reply), DAVID, [], ["x"], "notes", TODAY) is None


def test_card_at_the_limit_is_kept():
    card = "x" * context_ai.CARD_LIMIT
    assert context_ai.write_card(FakeClaude(card={"small_context": card}), DAVID, [], ["x"], "notes", TODAY) == card


context_ai.load_env()


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
def test_live_claude_facts_then_card():  # one real call pair; costs a few cents
    client = context_ai.make_client()
    lines = LINES + [TranscriptLine(speaker="David", text="I moved to Pittsburgh. I'm a nurse at UPMC now.")]
    facts = context_ai.extract_facts(client, DAVID, STORED, lines, TODAY, patient="Rose")
    assert facts
    card = context_ai.write_card(client, DAVID, STORED, facts, "conversation", TODAY)
    assert card and len(card) <= context_ai.CARD_LIMIT
    assert "David" not in card


def test_an_empty_model_override_means_the_default(monkeypatch):
    """docker-compose passes CONTEXT_MODEL through even when .env leaves it empty."""
    monkeypatch.setenv("CONTEXT_MODEL", "")
    assert context_ai.model_name() == context_ai.DEFAULT_MODEL
    monkeypatch.setenv("CONTEXT_MODEL", " claude-3.6-flash ")
    assert context_ai.model_name() == "claude-3.6-flash"

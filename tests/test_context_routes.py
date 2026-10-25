"""The person-context routes on the real backend (Postgres), with Gemini replaced by FakeGemini."""

import pytest

from backend import gemini
from tests.gemini_fakes import FakeGemini

CARD = "Lives in Pittsburgh · Works as a nurse | Ask about: the new job"
VISIT = {"lines": [{"speaker": "Rose", "text": "Did you move?"}, {"speaker": "David", "text": "Yes, to Pittsburgh."}]}


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGemini()
    monkeypatch.setattr(gemini, "get_client", lambda: fake)
    return fake


def new_person(client, name="David", relationship="grandson") -> int:
    return client.post("/people", json={"name": name, "relationship": relationship}).json()["id"]


def facts_of(client, pid):
    return [(f["text"], f["source"]) for f in client.get(f"/people/{pid}/facts").json()]


def test_enrollment_notes_become_facts_and_a_card(backend_client, fake):
    pid = new_person(backend_client)
    fake.replies = {"facts": {"new_facts": ["David bought a Tesla in October 2026.", "David loves cars."]}, "card": {"small_context": CARD}}
    r = backend_client.post(f"/people/{pid}/notes", json={"text": "I just bought a Tesla! I love cars."})
    assert r.status_code == 200
    assert r.json()["small_context"] == CARD
    assert facts_of(backend_client, pid) == [("David bought a Tesla in October 2026.", "notes"), ("David loves cars.", "notes")]
    assert fake.kinds() == ["facts", "card"]
    assert "Typed notes:\nI just bought a Tesla! I love cars." in fake.contents("facts")
    assert "from typed notes, not a conversation" in fake.contents("card")


def test_a_visit_adds_conversation_facts(backend_client, fake):
    rose = new_person(backend_client, "Rose", "user")
    pid = new_person(backend_client)
    fake.replies = {"facts": {"new_facts": ["David moved to Pittsburgh."]}, "card": {"small_context": CARD}}
    r = backend_client.post(f"/people/{pid}/conversation", json=VISIT)
    assert r.json()["small_context"] == CARD
    assert facts_of(backend_client, pid) == [("David moved to Pittsburgh.", "conversation")]
    assert facts_of(backend_client, rose) == []
    assert "Rose: Did you move?\nDavid: Yes, to Pittsburgh." in fake.contents("facts")
    assert "The patient is Rose" in fake.contents("facts")
    assert "from the latest conversation" in fake.contents("card")


def test_nothing_new_keeps_the_card_without_a_card_call(backend_client, fake):
    pid = new_person(backend_client)
    fake.replies = {"facts": {"new_facts": ["David moved to Pittsburgh."]}, "card": {"small_context": CARD}}
    backend_client.post(f"/people/{pid}/conversation", json=VISIT)
    fake.calls.clear()
    fake.replies["facts"] = {"new_facts": []}
    r = backend_client.post(f"/people/{pid}/conversation", json=VISIT)
    assert r.json()["small_context"] == CARD
    assert fake.kinds() == ["facts"]


def test_a_failed_facts_call_changes_nothing(backend_client, fake):
    pid = new_person(backend_client)
    fake.replies = {"facts": RuntimeError("network down"), "card": {"small_context": CARD}}
    r = backend_client.post(f"/people/{pid}/notes", json={"text": "I'm a nurse."})
    assert r.status_code == 200
    assert r.json()["small_context"] == ""
    assert facts_of(backend_client, pid) == []
    assert fake.kinds() == ["facts"]


@pytest.mark.parametrize("card", [RuntimeError("quota"), {"small_context": "x" * 201}, "not json"], ids=["error", "too-long", "bad-json"])
def test_a_failed_card_call_keeps_the_facts_and_the_old_card(backend_client, fake, card):
    pid = new_person(backend_client)
    backend_client.patch(f"/people/{pid}", json={"small_context": "Old card"})
    fake.replies = {"facts": {"new_facts": ["David is a nurse."]}, "card": card}
    r = backend_client.post(f"/people/{pid}/notes", json={"text": "I'm a nurse."})
    assert r.json()["small_context"] == "Old card"
    assert ("David is a nurse.", "notes") in facts_of(backend_client, pid)


def test_without_a_key_the_route_still_answers(backend_client, monkeypatch):
    def no_key():
        raise RuntimeError("GEMINI_API_KEY is not set")

    monkeypatch.setattr(gemini, "get_client", no_key)
    pid = new_person(backend_client)
    r = backend_client.post(f"/people/{pid}/notes", json={"text": "I'm a nurse."})
    assert r.status_code == 200 and r.json()["small_context"] == ""


def test_blank_text_makes_no_call(backend_client, fake):
    pid = new_person(backend_client)
    assert backend_client.post(f"/people/{pid}/notes", json={"text": "   "}).status_code == 200
    assert backend_client.post(f"/people/{pid}/conversation", json={"lines": []}).status_code == 200
    assert fake.calls == []


def test_unknown_person_is_404(backend_client, fake):
    assert backend_client.post("/people/999/notes", json={"text": "Hi"}).status_code == 404
    assert backend_client.post("/people/999/conversation", json=VISIT).status_code == 404
    assert backend_client.get("/people/999/facts").status_code == 404
    assert fake.calls == []


def test_deleting_a_fact(backend_client, fake):
    pid = new_person(backend_client)
    fake.replies = {"facts": {"new_facts": ["David is a nurse.", "David loves cars."]}, "card": {"small_context": CARD}}
    backend_client.post(f"/people/{pid}/notes", json={"text": "I'm a nurse and I love cars."})
    first = backend_client.get(f"/people/{pid}/facts").json()[0]["id"]
    assert backend_client.delete(f"/people/{pid}/facts/{first}").status_code == 204
    assert facts_of(backend_client, pid) == [("David loves cars.", "notes")]
    assert backend_client.delete(f"/people/{pid}/facts/{first}").status_code == 404

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


# -- the management view's routes: facts typed by the family, the card rewritten from them ----------

def test_the_family_adds_rewords_and_deletes_facts_directly(backend_client, fake):
    pid = new_person(backend_client)
    r = backend_client.post(f"/people/{pid}/facts", json={"text": "  David   plays the cello. "})
    assert r.status_code == 201, r.text
    fact = r.json()
    assert fact["text"] == "David plays the cello." and fact["source"] == "notes"
    assert backend_client.post(f"/people/{pid}/facts", json={"text": "david plays the cello."}).status_code == 409  # a repeat
    assert backend_client.post(f"/people/{pid}/facts", json={"text": "   "}).status_code == 422
    assert backend_client.post("/people/999/facts", json={"text": "Nobody."}).status_code == 404
    backend_client.post(f"/people/{pid}/facts", json={"text": "David lives in Erie."})

    r = backend_client.patch(f"/people/{pid}/facts/{fact['id']}", json={"text": "David plays the cello in a quartet."})
    assert r.status_code == 200 and r.json()["text"] == "David plays the cello in a quartet." and r.json()["id"] == fact["id"]
    assert backend_client.patch(f"/people/{pid}/facts/{fact['id']}", json={"text": "David lives in Erie."}).status_code == 409
    assert backend_client.patch(f"/people/{pid}/facts/999", json={"text": "x"}).status_code == 404
    other = new_person(backend_client, "Maria", "daughter")
    assert backend_client.patch(f"/people/{other}/facts/{fact['id']}", json={"text": "x"}).status_code == 404  # not hers
    assert facts_of(backend_client, pid) == [("David plays the cello in a quartet.", "notes"), ("David lives in Erie.", "notes")]
    assert fake.kinds() == []  # none of this went through Gemini

    assert backend_client.delete(f"/people/{pid}/facts/{fact['id']}").status_code == 204
    assert facts_of(backend_client, pid) == [("David lives in Erie.", "notes")]


def test_the_card_is_rewritten_from_the_stored_facts(backend_client, fake):
    pid = new_person(backend_client)
    assert backend_client.post(f"/people/{pid}/card").status_code == 422  # nothing to write from yet
    backend_client.post(f"/people/{pid}/facts", json={"text": "David lives in Erie."})
    backend_client.post(f"/people/{pid}/facts", json={"text": "David plays the cello."})
    fake.replies = {"card": {"small_context": "Lives in Erie · Plays the cello | Ask about: the quartet"}}
    r = backend_client.post(f"/people/{pid}/card")
    assert r.status_code == 200, r.text
    assert r.json()["small_context"] == "Lives in Erie · Plays the cello | Ask about: the quartet"
    assert fake.kinds() == ["card"]  # the facts are already stored: only the card call
    assert "David lives in Erie." in fake.contents("card") and "Just added, from typed notes" in fake.contents("card")
    assert facts_of(backend_client, pid) == [("David lives in Erie.", "notes"), ("David plays the cello.", "notes")]  # unchanged
    assert backend_client.post("/people/999/card").status_code == 404


def test_rewriting_the_card_without_gemini_keeps_the_old_one(backend_client, monkeypatch):
    monkeypatch.setattr(gemini, "get_client", lambda: (_ for _ in ()).throw(RuntimeError("GEMINI_API_KEY is not set")))
    pid = new_person(backend_client)
    backend_client.patch(f"/people/{pid}", json={"small_context": "Your grandson."})
    r = backend_client.post(f"/people/{pid}/card")
    assert r.status_code == 503 and "Gemini" in r.json()["detail"]
    assert backend_client.get(f"/people/{pid}").json()["small_context"] == "Your grandson."


def test_one_person_and_their_recording_can_be_fetched(backend_client):
    from contract.fakes import make_wav

    pid = new_person(backend_client)
    assert backend_client.get(f"/people/{pid}").json()["name"] == "David"
    assert backend_client.get("/people/999").status_code == 404
    wav = make_wav(2.0)
    sid = backend_client.post(f"/people/{pid}/voice", files={"file": ("v.wav", wav, "audio/wav")}).json()["voice_sample_id"]
    r = backend_client.get(f"/people/{pid}/voice/{sid}/audio")
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/wav") and r.content == wav
    other = new_person(backend_client, "Maria", "daughter")
    assert backend_client.get(f"/people/{other}/voice/{sid}/audio").status_code == 404  # not hers
    assert backend_client.delete(f"/people/{pid}/voice/{sid}").status_code == 204
    assert backend_client.get(f"/people/{pid}/voice/{sid}/audio").status_code == 404

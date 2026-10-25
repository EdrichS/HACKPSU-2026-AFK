"""The glasses user's own notes go through Gemini like everyone else's, as facts about themselves."""

from datetime import date

from backend import gemini
from db.people import create_person
from tests.gemini_fakes import FakeGemini


def test_the_users_own_notes_are_facts_about_the_patient(conn, test_db):
    import psycopg_pool

    rose = create_person(conn, "Rose", "user")
    conn.commit()
    fake = FakeGemini(facts={"new_facts": ["Rose is a botanist.", "Rose has a cat called Mabel."]}, card={"small_context": "Botanist · Cat Mabel | Ask about: the garden"})
    pool = psycopg_pool.ConnectionPool(test_db, min_size=1, max_size=2, open=True)
    try:
        person = gemini.update_context(pool, rose.id, "I am a botanist and I have a cat called Mabel.", "notes", client=fake, today=date(2026, 10, 25))
    finally:
        pool.close()
    assert fake.kinds() == ["facts", "card"]
    request = fake.contents("facts")
    assert "Rose, the patient themselves" in request and "rule 1 is reversed" in request
    assert "The patient is Rose; lines from" not in request  # not told to ignore her own words
    assert "Rose, the patient themselves" in fake.contents("card")
    assert person.small_context == "Botanist · Cat Mabel | Ask about: the garden"
    conn.rollback()
    assert [r[0] for r in conn.execute("SELECT text FROM facts WHERE person_id = %s ORDER BY id", (rose.id,))] == ["Rose is a botanist.", "Rose has a cat called Mabel."]


def test_a_visitors_notes_still_name_the_patient(conn, test_db):
    import psycopg_pool

    create_person(conn, "Rose", "user")
    david = create_person(conn, "David", "grandson")
    conn.commit()
    fake = FakeGemini(facts={"new_facts": ["David is a nurse."]}, card={"small_context": "Nurse | Ask about: work"})
    pool = psycopg_pool.ConnectionPool(test_db, min_size=1, max_size=2, open=True)
    try:
        gemini.update_context(pool, david.id, "I'm a nurse.", "notes", client=fake)
    finally:
        pool.close()
    request = fake.contents("facts")
    assert "David, the patient's grandson" in request and "The patient is Rose" in request
    conn.rollback()


def test_enroll_sends_the_users_notes_through_gemini(backend_client, backend_module, monkeypatch, conn):
    """The wizard's setup for the wearer: /enroll with relationship 'user' and notes."""
    from db.context import list_facts

    fake = FakeGemini(facts={"new_facts": ["Rose likes the garden."]}, card={"small_context": "Likes the garden"})
    monkeypatch.setattr("backend.gemini.get_client", lambda: fake)
    backend_module.app.state.gemini = True
    r = backend_client.post("/enroll", data={"name": "Rose", "relationship": "user", "notes": "I like the garden."})
    assert r.status_code == 201, r.text
    assert r.json()["person"]["small_context"] == "Likes the garden" and r.json()["facts"] == 1
    assert "Rose, the patient themselves" in fake.contents("facts")
    assert [f.text for f in list_facts(conn, r.json()["person"]["id"])] == ["Rose likes the garden."]

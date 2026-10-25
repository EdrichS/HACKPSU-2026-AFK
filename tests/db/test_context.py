import pytest

from db.context import add_facts, delete_fact, list_facts, save_context
from db.errors import NotFound
from db.people import create_person, get_person


def test_facts_come_back_oldest_first(conn):
    pid = create_person(conn, "David", "grandson").id
    save_context(conn, pid, ["Moved to Pittsburgh"], "conversation", "David is your grandson.")
    save_context(conn, pid, ["Works as a nurse"], "notes", "David is your grandson. He is a nurse.")
    assert [f.text for f in list_facts(conn, pid)] == ["Moved to Pittsburgh", "Works as a nurse"]


def test_save_context_replaces_the_card(conn):
    pid = create_person(conn, "David", "grandson").id
    person = save_context(conn, pid, ["Works as a nurse"], "notes", "David is your grandson. He is a nurse.")
    assert person.small_context == "David is your grandson. He is a nurse."


def test_a_repeated_fact_is_not_added_twice(conn):
    pid = create_person(conn, "David", "grandson").id
    save_context(conn, pid, ["Works as a nurse"], "conversation", "Card one.")
    save_context(conn, pid, ["works as a nurse "], "conversation", "Card two.")
    assert [f.text for f in list_facts(conn, pid)] == ["Works as a nurse"]


def test_a_bad_reply_changes_nothing(conn):                             # Review Focus 5
    pid = create_person(conn, "David", "grandson").id
    with pytest.raises(ValueError):
        save_context(conn, pid, ["Works as a nurse"], "conversation", "x" * 301)
    with pytest.raises(ValueError):
        save_context(conn, pid, ["   "], "conversation", "David is your grandson.")
    assert get_person(conn, pid).small_context == "" and list_facts(conn, pid) == []


def test_a_blank_card_keeps_the_old_one(conn):
    pid = create_person(conn, "David", "grandson").id
    save_context(conn, pid, [], "notes", "David is your grandson.")
    with pytest.raises(ValueError):
        save_context(conn, pid, ["Works as a nurse"], "conversation", "   ")
    assert get_person(conn, pid).small_context == "David is your grandson."
    assert list_facts(conn, pid) == []


def test_deleting_one_fact(conn):
    pid = create_person(conn, "David", "grandson").id
    save_context(conn, pid, ["Moved to Pittsburgh", "Works as a nurse"], "notes", "Card.")
    first = list_facts(conn, pid)[0].id
    assert delete_fact(conn, pid, first) is True
    assert [f.text for f in list_facts(conn, pid)] == ["Works as a nurse"]
    assert delete_fact(conn, pid, first) is False


def test_context_for_unknown_person(conn):
    with pytest.raises(NotFound, match="person"):
        save_context(conn, 999, ["Works as a nurse"], "notes", "Card.")
    with pytest.raises(NotFound, match="person"):
        add_facts(conn, 999, ["Works as a nurse"], "notes")


def test_add_facts_keeps_the_card(conn):
    pid = create_person(conn, "David", "grandson").id
    save_context(conn, pid, [], "notes", "Card.")
    person = add_facts(conn, pid, ["Works as a nurse", "works as a nurse"], "conversation")
    assert person.small_context == "Card."
    assert [(f.text, f.source) for f in list_facts(conn, pid)] == [("Works as a nurse", "conversation")]
    with pytest.raises(ValueError):
        add_facts(conn, pid, ["x" * 301], "notes")

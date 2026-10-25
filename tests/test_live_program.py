"""The live program's pieces, without a camera, a microphone or a network: presence, visits,
the summary parsing and storage, Nova's database tools, and the database matchers."""

import logging
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import psycopg_pool
import pytest

from contract.live import EMPTY_ROOM_TEXT, UNKNOWN_TEXT, PresentPerson
from db.context import list_facts
from db.people import create_person, get_person, update_person
from live.presence import Presence
from live.visit import Visit, save_visit

ROOT = Path(__file__).resolve().parents[1]
DAVID = PresentPerson(person_id=1, name="David", relationship="grandson", small_context="")
MARIA = PresentPerson(person_id=2, name="Maria", relationship="daughter", small_context="")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# -- presence --------------------------------------------------------------------------------

def test_a_face_needs_two_sightings_and_is_announced_once():
    clock = Clock()
    p = Presence(clock=clock)
    assert p.saw(DAVID, "face") is None and p.present() == []
    clock.t += 0.5
    assert p.saw(DAVID, "face") == "Here's David, your grandson."
    assert p.present() == [DAVID]
    for _ in range(50):  # staying in view never repeats the announcement
        clock.t += 1
        assert p.saw(DAVID, "face") is None


def test_the_wearer_is_never_announced_or_listed():
    p = Presence(clock=Clock(), user_id=MARIA.person_id)
    assert p.saw(MARIA, "voice") is None
    assert p.present() == []
    assert p.saw(DAVID, "voice") == "Here's David, your grandson."


def test_a_voice_counts_at_once():
    p = Presence(clock=Clock())
    assert p.saw(MARIA, "voice") == "Here's Maria, your daughter."


def test_leaving_and_coming_back_much_later_is_announced_again():
    clock = Clock()
    p = Presence(gone_after=20, reannounce=300, clock=clock)
    p.saw(DAVID, "voice")
    clock.t += 30
    assert p.present() == []  # gone
    assert p.saw(DAVID, "voice") is None  # back soon: no repeat
    clock.t += 300
    assert p.saw(DAVID, "voice") == "Here's David, your grandson."


def test_each_arrival_logs_how_long_naming_took(caplog):
    clock = Clock()
    p = Presence(clock=clock)
    with caplog.at_level(logging.INFO, logger="live.presence"):
        p.saw(DAVID, "face")
        clock.t += 0.8
        p.saw(DAVID, "face")  # the second sighting names him
        p.saw(MARIA, "voice")  # a voice counts at once
        clock.t += 330  # gone, and back after more than five minutes: timed from the return
        p.saw(DAVID, "face")
        clock.t += 0.5
        p.saw(DAVID, "face")
    assert [r.getMessage() for r in caplog.records if r.name == "live.presence"] == [
        "David named by face, 0.8 s after first seen or heard",
        "Maria named by voice, 0.0 s after first seen or heard",
        "David named by face, 0.5 s after first seen or heard",
    ]


def test_who_answer_names_everyone_in_arrival_order():
    clock = Clock()
    p = Presence(clock=clock)
    p.saw(MARIA, "voice")
    clock.t += 1
    p.saw(DAVID, "voice")
    assert p.who_answer() == "That's Maria, your daughter, and David, your grandson."
    clock.t += 100
    assert p.who_answer() == EMPTY_ROOM_TEXT


def test_an_unknown_face_is_called_out_only_after_a_while():
    clock = Clock()
    p = Presence(unknown_after=4, unknown_cooldown=60, clock=clock)
    assert p.unknown_face(True) is None
    clock.t += 2
    assert p.unknown_face(False) is None  # it left: the clock restarts
    assert p.unknown_face(True) is None
    clock.t += 5
    assert p.unknown_face(True) == UNKNOWN_TEXT
    clock.t += 5
    assert p.unknown_face(True) is None  # within the cooldown


# -- the visit and its summary (the context owner's Claude flow) ---------------------------------

def test_visit_keeps_lines_and_known_people():
    v = Visit()
    v.add("Rose", 3, "Did you move?")
    v.add("David", 1, "Yeah, last month.")
    v.add("David", 1, "   ")
    v.add("Someone", None, "Is this seat free?")  # a voice nobody enrolled: kept here, never sent to Gemini
    v.note(DAVID)
    assert [(l.speaker, l.text) for l in v.transcript()] == [("Rose", "Did you move?"), ("David", "Yeah, last month.")]
    assert [l.speaker for l in v.lines] == ["Rose", "David", "Someone"]
    assert list(v.people) == [1]


@pytest.fixture
def pool(test_db):
    p = psycopg_pool.ConnectionPool(test_db, min_size=1, max_size=3, open=True)
    yield p
    p.close()


def test_save_visit_hands_the_transcript_to_claude_and_stores_facts_and_card(conn, pool):
    from tests.claude_fakes import FakeClaude

    david = create_person(conn, "David", "grandson")
    rose = create_person(conn, "Rose", "user")
    update_person(conn, david.id, small_context="David is your grandson.")
    conn.commit()
    fake = FakeClaude(
        facts={"new_facts": ["David moved to Pittsburgh in September 2026.", "David works as a nurse."]},
        card={"small_context": "Last spoke about: moving · Works as a nurse | Ask about: Pittsburgh"},
    )
    v = Visit()
    v.add("Rose", rose.id, "Did you move?")
    v.add("David", david.id, "Yeah, last month. I'm a nurse now.")
    v.note(PresentPerson(person_id=david.id, name="David", relationship="grandson", small_context=""))
    v.note(PresentPerson(person_id=rose.id, name="Rose", relationship="user", small_context=""))
    results = save_visit(pool, v, user_id=rose.id, client=fake, today=date(2026, 10, 24))
    assert [r.person.name for r in results] == ["David"]  # the user is never a visitor
    [r] = results
    assert r.new_facts == ["David moved to Pittsburgh in September 2026.", "David works as a nurse."]
    assert r.updated.small_context == "Last spoke about: moving · Works as a nurse | Ask about: Pittsburgh"
    assert fake.kinds() == ["facts", "card"]
    assert "David: Yeah, last month. I'm a nurse now." in fake.contents("facts")
    assert "The patient is Rose" in fake.contents("facts")
    conn.rollback()  # see the pool's committed rows, not this connection's snapshot
    assert [(f.text, f.source) for f in list_facts(conn, david.id)] == [
        ("David is your grandson.", "notes"),
        ("David moved to Pittsburgh in September 2026.", "conversation"),
        ("David works as a nurse.", "conversation"),
    ]


def test_save_visit_keeps_everything_when_claude_fails(conn, pool):
    from tests.claude_fakes import FakeClaude

    david = create_person(conn, "David", "grandson")
    update_person(conn, david.id, small_context="David is your grandson.")
    conn.commit()
    v = Visit()
    v.add("David", david.id, "Hello there.")
    v.note(PresentPerson(person_id=david.id, name="David", relationship="grandson", small_context=""))
    [result] = save_visit(pool, v, client=FakeClaude(facts=RuntimeError("boom")))
    assert result.new_facts == [] and result.updated is None
    conn.rollback()
    assert get_person(conn, david.id).small_context == "David is your grandson."
    assert [f.source for f in list_facts(conn, david.id)] == ["notes"]


def test_save_visit_with_nothing_new_changes_nothing(conn, pool):
    from tests.claude_fakes import FakeClaude

    david = create_person(conn, "David", "grandson")
    update_person(conn, david.id, small_context="Works as a nurse | Ask about: the garden")
    conn.commit()
    v = Visit()
    v.add("David", david.id, "Hi again.")
    v.note(PresentPerson(person_id=david.id, name="David", relationship="grandson", small_context=""))
    fake = FakeClaude(facts={"new_facts": []})
    [result] = save_visit(pool, v, client=fake)
    assert result.updated is None and fake.kinds() == ["facts"]  # a repeat visit keeps the card, no card call


# -- Nova's tools -----------------------------------------------------------------------------

def test_nova_tools_read_the_database(conn, pool):
    from live.nova import NovaBrain

    david = create_person(conn, "David", "grandson")
    update_person(conn, david.id, small_context="David is your grandson. He is a nurse.")
    conn.commit()
    presence = Presence(clock=Clock())
    nova = NovaBrain(client=None, pool=pool, presence=presence, user_name="Rose")
    assert "David, Rose's grandson: David is your grandson. He is a nurse." in nova.tool_list_people()
    about = nova.tool_person_context("david")
    assert "David, Rose's grandson (not seen right now)" in about
    assert "- David is your grandson. He is a nurse." in about  # the hand-written card is also a fact
    assert "No one called 'Zed'" in nova.tool_person_context("Zed")
    assert nova.tool_who_is_here() == EMPTY_ROOM_TEXT
    presence.saw(PresentPerson(person_id=david.id, name="David", relationship="grandson", small_context=""), "voice")
    assert nova.tool_who_is_here() == "That's David, your grandson."
    assert "(here right now)" in nova.tool_person_context("David")
    assert [t.name for t in nova.tools] == ["list_people", "person_context", "who_is_here"]
    conn.rollback()


def test_nova_says_who_is_here_when_nobody_has_that_name(pool):
    from live.nova import NovaBrain

    presence = Presence(clock=Clock())
    nova = NovaBrain(client=None, pool=pool, presence=presence, user_name="Rose")
    assert nova.tool_person_context("Zed") == f"No one called 'Zed' is in the database. Here right now: {EMPTY_ROOM_TEXT}"
    presence.saw(DAVID, "voice")
    assert nova.tool_person_context("Zed").endswith("Here right now: That's David, your grandson.")


def test_nova_introduces_herself_once_per_visit(pool):
    from live.nova import NovaBrain
    from tests.helpers import FakeNova

    nova = NovaBrain(client=FakeNova("David is your grandson."), pool=pool, presence=Presence(clock=Clock()), user_name="Rose")
    assert nova.answer("who is David?") == "I'm Nova, the helper in your glasses. David is your grandson."
    assert nova.answer("who is David?") == "David is your grandson."
    nova.new_visit()
    assert nova.answer("who is David?") == "I'm Nova, the helper in your glasses. David is your grandson."


def test_nova_is_told_never_to_claim_to_be_a_person(pool):
    from live.nova import NovaBrain
    from tests.helpers import FakeNova

    claude = FakeNova("I'm the helper in your glasses.")
    NovaBrain(client=claude, pool=pool, presence=Presence(clock=Clock()), user_name="Rose").answer("are you a real person?")
    [call] = claude.calls
    assert "never claim to be a person" in call["system"][0]["text"]


def test_python_m_live_lets_nova_introduce_herself_again_after_a_visit(pool):
    from live.cli import Session
    from live.nova import NovaBrain
    from tests.helpers import FakeNova

    session = Session(SimpleNamespace(log=None), pool, "Rose", None)
    session.nova = NovaBrain(FakeNova("Hello."), pool, session.presence, user_name="Rose")
    assert session.nova.answer("hi there") == "I'm Nova, the helper in your glasses. Hello."
    session.end_visit("you asked")
    assert session.nova.answer("hi there") == "I'm Nova, the helper in your glasses. Hello."


# -- the matchers against real samples ---------------------------------------------------------

ASTRONAUT = ROOT / "facial-recognition-foundation-46999b" / "tests" / "fixtures" / "astronaut.jpg"
SPEECH = ROOT / "hackpsu_voice_rec" / "models" / "sherpa-onnx-moonshine-base-en-int8" / "test_wavs" / "1.wav"


def test_a_known_face_is_named_from_the_database(conn, pool):
    try:
        from embedders.face import FaceRecEmbedder
    except ImportError as e:
        pytest.skip(str(e))
    from db.photos import assign_face, save_photo
    from live.faces import FaceIdentifier

    face = FaceRecEmbedder()
    data = ASTRONAUT.read_bytes()
    found = face.detect_faces(data)
    eileen = create_person(conn, "Eileen", "friend")
    photo = save_photo(conn, "data/photos/astronaut.jpg", 512, 512, found, face.spec.model)
    assign_face(conn, photo.faces[0].face_id, eileen.id)  # label the first face only
    conn.commit()
    try:
        person, verdict, distance = FaceIdentifier(face, pool).identify(found[0])
        assert verdict == "named" and person.name == "Eileen" and distance < 1e-6
        if len(found) > 1:  # the other face in the photo is unlabelled: never named
            other = FaceIdentifier(face, pool).identify(found[1])
            assert other[0] is None
    finally:
        conn.execute("DELETE FROM photos")
        conn.commit()


def test_a_known_voice_is_named_from_the_database(conn, pool):
    if not SPEECH.exists():
        pytest.skip(f"{SPEECH} not downloaded")
    from embedders.voice import VoiceRecEmbedder, decode_wav
    from db.voice import add_voice
    from live.voices import VoiceIdentifier

    try:
        voice = VoiceRecEmbedder()
    except FileNotFoundError as e:
        pytest.skip(str(e))
    samples = decode_wav(SPEECH.read_bytes())
    half = len(samples) // 2
    reader = create_person(conn, "Reader", "friend")
    add_voice(conn, reader.id, "data/voice/reader.wav", voice.embed_samples(samples[:half]), voice.spec.model)
    conn.commit()
    try:
        person, verdict, distance = VoiceIdentifier(voice, pool).identify(samples[half:])
        assert verdict == "named" and person.name == "Reader" and distance < voice.spec.cutoff
        unknown = VoiceIdentifier(voice, pool).identify(np.random.default_rng(0).normal(0, 0.05, 16000 * 3).astype(np.float32))
        assert unknown[0] is None  # noise is nobody
    finally:
        conn.execute("DELETE FROM people")
        conn.commit()


# -- voice resolution and the recording source ----------------------------------------------------

def _cand(pid, name, distance):
    from db.match import Candidate

    return Candidate(pid, name, "friend", "", distance)


def test_resolve_voice_rescues_a_clear_winner_just_past_the_cutoff():
    from live.voices import resolve_voice

    best, verdict = resolve_voice([_cand(1, "A", 0.60), _cand(2, "B", 0.95)], cutoff=0.55, margin=0.10)
    assert verdict == "named" and best.name == "A"
    best, verdict = resolve_voice([_cand(1, "A", 0.60), _cand(2, "B", 0.70)], cutoff=0.55, margin=0.10)
    assert best is None and verdict == "no_match"  # too close to the runner-up to rescue
    best, verdict = resolve_voice([_cand(1, "A", 0.70)], cutoff=0.55, margin=0.10)
    assert best is None  # past the rescue floor


def test_resolve_voice_breaks_a_tie_with_who_is_on_camera():
    from live.voices import resolve_voice

    close = [_cand(1, "A", 0.30), _cand(2, "B", 0.35)]
    assert resolve_voice(close, 0.55, 0.10)[1] == "not_sure"
    best, verdict = resolve_voice(close, 0.55, 0.10, present_ids={2})
    assert verdict == "named" and best.name == "B"
    assert resolve_voice(close, 0.55, 0.10, present_ids={1, 2})[0] is None  # both here: still unsure
    assert resolve_voice([], 0.55, 0.10)[1] == "no_match"


def test_a_recording_runs_through_the_listener_without_a_camera(conn, pool):
    if not SPEECH.exists():
        pytest.skip(f"{SPEECH} not downloaded")
    from embedders.voice import VoiceRecEmbedder, decode_wav, encode_wav
    from db.voice import add_voice
    from live.voices import VoiceIdentifier, VoiceListener

    try:
        voice = VoiceRecEmbedder()
    except FileNotFoundError as e:
        pytest.skip(str(e))
    samples = decode_wav(SPEECH.read_bytes())
    half = len(samples) // 2
    reader = create_person(conn, "Reader", "friend")
    add_voice(conn, reader.id, "data/voice/reader.wav", voice.embed_samples(samples[:half]), voice.spec.model)
    conn.commit()
    clip = ROOT / "data" / "test_reader_tail.wav"
    clip.parent.mkdir(exist_ok=True)
    clip.write_bytes(encode_wav(samples[half:]))
    heard = []
    ended = []
    try:
        listener = VoiceListener(VoiceIdentifier(voice, pool), None, heard.append, source=clip, speed=50.0, on_end=lambda: ended.append(True))
        listener.start()
        listener.join(timeout=60)
        assert listener.error is None and ended == [True]
        assert heard, "no utterance came out of the recording"
        assert all(u.person is not None and u.person.name == "Reader" for u in heard)
        assert all(u.verdict == "named" for u in heard)
    finally:
        clip.unlink(missing_ok=True)
        conn.execute("DELETE FROM people")
        conn.commit()

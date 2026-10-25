"""The /live WebSocket on the real backend, with the fake embedders (the same bytes always give
the same embedding, so a frame of an enrolled picture is a match)."""

import json
import logging
from pathlib import Path

import pytest

from contract.fakes import make_wav
from tests.helpers import PNG_1x1, b64

ROOT = Path(__file__).resolve().parents[1]
SPEECH = ROOT / "hackpsu_voice_rec" / "models" / "sherpa-onnx-moonshine-base-en-int8" / "test_wavs" / "1.wav"


def frame(png: bytes = PNG_1x1, ts: int = 1) -> str:
    return json.dumps({"type": "frame", "ts": ts, "jpeg": b64(png)})


def receive_until(ws, kind: str) -> list[dict]:
    """Messages up to and including the first of type `kind`."""
    out = []
    while True:
        m = ws.receive_json()
        out.append(m)
        if m["type"] == kind:
            return out


@pytest.fixture
def maya(backend_client, monkeypatch):
    import backend.enroll_api as api

    monkeypatch.setattr(api, "trim_speech", lambda samples: samples)
    notes = "Anita's daughter, your oldest grandchild. Studying nursing, in her final year. Visits most Sundays after lunch."
    r = backend_client.post(
        "/enroll",
        data={"name": "Maya", "relationship": "granddaughter", "notes": notes},
        files=[("photos", ("p.png", PNG_1x1, "image/png")), ("voice", ("v.wav", make_wav(5.0), "audio/wav"))],
    )
    assert r.status_code == 201, r.text
    return r.json()["person"]


def test_the_server_shows_how_long_naming_took(backend_module):
    # uvicorn shows only its own info lines; the server lets this one through, and captions stay out
    assert logging.getLogger("live.presence").getEffectiveLevel() == logging.INFO


def test_a_known_face_is_named_announced_and_carded(backend_client, maya):
    with backend_client.websocket_connect("/live") as ws:
        ws.send_text(frame())
        [first] = receive_until(ws, "present")
        assert first["people"] == []  # one sighting is not enough to be sure
        assert first["faces"] == [{"box": {"x": 0, "y": 0, "width": 1, "height": 1}, "state": "named", "person_id": maya["id"]}]
        ws.send_text(frame(ts=2))
        msgs = receive_until(ws, "arrived")
        present = next(m for m in msgs if m["type"] == "present")
        [person] = present["people"]
        assert (person["name"], person["relationship"]) == ("Maya", "granddaughter")
        assert person["facts"] == ["Anita's daughter, your oldest grandchild.", "Studying nursing, in her final year.", "Visits most Sundays after lunch."]
        arrived = msgs[-1]
        assert arrived["via"] == "face" and arrived["text"] == "Here's Maya, your granddaughter."
        ws.send_text('{"type":"who"}')
        assert ws.receive_json() == {"type": "who_answer", "text": "That's Maya, your granddaughter."}


def test_a_strange_face_is_unsure_and_the_room_is_empty(backend_client):
    with backend_client.websocket_connect("/live") as ws:
        ws.send_text(frame())
        [present] = receive_until(ws, "present")
        assert present["people"] == [] and present["faces"][0]["state"] == "unsure"
        ws.send_text('{"type":"who"}')
        assert ws.receive_json()["text"] == "I don't see anyone I know right now."


def test_a_bad_message_keeps_the_socket_open(backend_client, backend_module, monkeypatch):
    def broken(image):
        raise ValueError("bad image")

    with backend_client.websocket_connect("/live") as ws:
        ws.send_text('{"type":"dance"}')
        assert ws.receive_json()["type"] == "error"
        monkeypatch.setattr(backend_module.face_embedder, "detect_faces", broken)  # the fake would "see" a face in anything
        ws.send_text(json.dumps({"type": "frame", "ts": 1, "jpeg": b64(b"not a jpeg")}))
        assert [ws.receive_json()["type"], ws.receive_json()["type"]] == ["present", "error"]  # every frame gets a present
        monkeypatch.undo()
        ws.send_text("not even json")
        assert ws.receive_json()["type"] == "error"
        ws.send_text('{"type":"who"}')
        assert ws.receive_json()["type"] == "who_answer"


def test_speech_becomes_captions_attributed_to_the_user(backend_client, backend_module):
    if not SPEECH.exists():
        pytest.skip(f"{SPEECH} not downloaded")
    if backend_module.app.state.transcriber is None:
        pytest.skip("no speech-to-text model")
    wav = SPEECH.read_bytes()
    with backend_client.websocket_connect("/live") as ws:
        ws.send_text(json.dumps({"type": "audio", "ts": 1, "wav": b64(wav)}))
        ws.send_text(json.dumps({"type": "audio", "ts": 2, "wav": b64(make_wav(2.0))}))  # silence closes the last utterance
        ws.send_text('{"type":"who"}')
        msgs = receive_until(ws, "who_answer")
    captions = [m for m in msgs if m["type"] == "caption"]
    assert captions, msgs
    assert all(c["speaker"] is None and c["person_id"] is None and c["final"] is True for c in captions)  # nobody is registered
    assert any(len(c["text"].split()) >= 3 for c in captions)
    assert all(c["end"] > c["start"] >= 0 for c in captions)


def test_end_visit_sends_the_transcript_to_claude_and_reports_what_was_saved(backend_client, backend_module, monkeypatch, maya):
    """The socket's end_visit, driven directly: the transcript goes to backend.context_ai, and the
    frontend gets one visit_saved per visitor with the new facts and card."""
    from backend.live_api import LiveSession
    from contract.live import PresentPerson, VisitSaved
    from tests.claude_fakes import FakeClaude

    fake = FakeClaude(facts={"new_facts": ["Maya brought photos from a beach trip."]}, card={"small_context": "Last spoke about: the beach trip | Ask about: the photos"})
    monkeypatch.setattr("backend.context_ai.get_client", lambda: fake)
    session = LiveSession(backend_module.app.state)
    session.visit.note(PresentPerson(person_id=maya["id"], name="Maya", relationship="granddaughter", small_context=""))
    session.visit.add("Maya", maya["id"], "Hi Grandma! I brought the photos from our beach trip.")
    session.visit.add("User", None, "Oh, how lovely.")
    [saved] = session.end_visit()
    assert isinstance(saved, VisitSaved)
    assert (saved.name, saved.new_facts, saved.small_context) == ("Maya", ["Maya brought photos from a beach trip."], "Last spoke about: the beach trip | Ask about: the photos")
    assert "Maya: Hi Grandma! I brought the photos from our beach trip." in fake.contents("facts")
    assert "Oh, how lovely." not in fake.contents("facts")  # a voice nobody enrolled stays on the machine
    assert session.visit.lines == []  # a fresh visit starts
    [transcript] = (backend_module.app.state.data_dir / "visits").glob("*.txt")
    assert "Maya: Hi Grandma! I brought the photos from our beach trip." in transcript.read_text()
    assert "User: Oh, how lovely." in transcript.read_text()  # the local file keeps every line
    assert backend_client.get("/people").json()[0]["small_context"] == "Last spoke about: the beach trip | Ask about: the photos"
    assert [f["text"] for f in backend_client.get(f"/people/{maya['id']}/facts").json()][-1] == "Maya brought photos from a beach trip."


def test_a_quiet_visit_ends_by_itself(backend_client, backend_module, monkeypatch, maya):
    import time

    from backend.live_api import LiveSession
    from contract.live import PresentPerson, Who
    from tests.claude_fakes import FakeClaude

    fake = FakeClaude(facts={"new_facts": ["Maya visits on Sundays."]}, card={"small_context": "Visits on Sundays"})
    monkeypatch.setattr("backend.context_ai.get_client", lambda: fake)
    session = LiveSession(backend_module.app.state, visit_idle=60.0)
    session.visit.note(PresentPerson(person_id=maya["id"], name="Maya", relationship="granddaughter", small_context=""))
    session.visit.add("Maya", maya["id"], "See you next Sunday, Grandma.")
    assert session.handle(Who())[0].type == "who_answer"  # just spoken: the visit goes on
    session.visit.lines[-1].t = time.time() - 61
    out = session.handle(Who())
    assert [m.type for m in out] == ["visit_saved", "who_answer"]
    assert out[0].new_facts == ["Maya visits on Sundays."] and session.visit.lines == []


class FakeSpeechmatics:
    """Stands in for voice_rec.cloud.LiveSession: every audio block becomes a partial and a finished turn by S1."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.sent_samples = 0
        self.closed = False

    def _flush_turn(self) -> None:  # the real session's hooks that cloud_captions calls on a clock and on end_visit
        pass

    def _idle_check(self) -> None:
        pass

    async def run(self, audio, stop):
        from voice_rec.cloud import Turn, Word

        namer, on_partial, on_turn = self.kwargs["namer"], self.kwargs["on_partial"], self.kwargs["on_turn"]
        n = 0
        async for block in audio:
            if stop():
                break
            self.sent_samples += len(block)
            named = namer.offer("S1", block)
            if named:
                self.kwargs["on_event"]("mapping", {"label": "S1", "speaker": named})
            n += 1
            on_partial("S1", "Hi Grandma, I")
            on_turn(Turn("S1", [Word("Hi", 0.0, 0.4, "S1"), Word("Grandma,", 0.5, 1.0, "S1"), Word(f"visit {n}.", 1.1, 1.6, "S1", is_eos=True)]), "S1")
        self.closed = True
        return []


def test_cloud_captions_arrive_live_and_name_the_voice(backend_client, backend_module, monkeypatch, maya):
    """With a Speechmatics key, audio is streamed and captions come back as partials then finished turns;
    the diarization label is matched against voice_samples once it has heard enough."""
    import backend.cloud_captions as cloud

    made = []
    monkeypatch.setattr(cloud, "RawLabelSession", lambda **kw: made.append(FakeSpeechmatics(**kw)) or made[-1])
    backend_module.app.state.speechmatics_key = "test-key"
    try:
        with backend_client.websocket_connect("/live") as ws:
            ws.send_text(json.dumps({"type": "audio", "ts": 1, "wav": b64(make_wav(5.0))}))  # Maya's enrolled recording
            msgs = receive_until(ws, "caption")
            msgs += receive_until(ws, "caption")
            kinds = [m["type"] for m in msgs]
            assert "arrived" in kinds, msgs  # a clear match names S1 on the first attempt: Maya, by voice
            partial = next(m for m in msgs if m["type"] == "caption" and not m["final"])
            assert partial["text"] == "Hi Grandma, I" and partial["speaker"] == "Maya"
            final = [m for m in msgs if m["type"] == "caption" and m["final"]][-1]
            assert final["speaker"] == "Maya" and final["person_id"] == maya["id"] and final["text"] == "Hi Grandma, visit 1."
            ws.send_text(json.dumps({"type": "audio", "ts": 2, "wav": b64(make_wav(5.0))}))
            msgs = receive_until(ws, "caption")
            msgs += receive_until(ws, "caption")
            assert "arrived" not in [m["type"] for m in msgs]  # announced once
            final = [m for m in msgs if m["type"] == "caption" and m["final"]][-1]
            assert final["speaker"] == "Maya" and final["text"] == "Hi Grandma, visit 2."
            ws.send_text('{"type":"who"}')
            who = receive_until(ws, "who_answer")[-1]
            assert "Maya" in who["text"]
            ws.send_text('{"type":"end_visit"}')  # written to the transcript file before the next reply
            ws.send_text('{"type":"who"}')
            receive_until(ws, "who_answer")
    finally:
        backend_module.app.state.speechmatics_key = None
    assert len(made) == 1 and made[0].closed
    assert made[0].kwargs["extra_vocab"] == ["Maya", "Nova"]
    visits = list((Path(backend_module.app.state.data_dir) / "visits").glob("*.txt"))
    assert len(visits) == 1 and "Maya: Hi Grandma, visit 2." in visits[0].read_text()


def test_lines_said_before_a_voice_was_named_become_theirs(backend_client, backend_module, monkeypatch, maya):
    """The first attempt matched nobody (a cough, a short word); the second names Maya, and the
    transcript line from before is hers too, so the visit summary doesn't lose it."""
    import backend.cloud_captions as cloud
    from live.voices import VoiceIdentifier

    real = VoiceIdentifier.identify
    calls = []

    def flaky(self, samples):
        calls.append(1)
        return (None, "no_match", 0.9) if len(calls) == 1 else real(self, samples)

    monkeypatch.setattr(VoiceIdentifier, "identify", flaky)
    monkeypatch.setattr(cloud, "RawLabelSession", lambda **kw: FakeSpeechmatics(**kw))
    backend_module.app.state.speechmatics_key = "test-key"
    try:
        with backend_client.websocket_connect("/live") as ws:
            ws.send_text(json.dumps({"type": "audio", "ts": 1, "wav": b64(make_wav(5.0))}))
            first = [m for m in receive_until(ws, "caption") + receive_until(ws, "caption") if m["type"] == "caption" and m["final"]][-1]
            assert first["speaker"] is None and first["text"] == "Hi Grandma, visit 1."
            ws.send_text(json.dumps({"type": "audio", "ts": 2, "wav": b64(make_wav(5.0))}))
            msgs = receive_until(ws, "caption") + receive_until(ws, "caption")
            if "arrived" not in [m["type"] for m in msgs]:
                msgs += receive_until(ws, "arrived")
            assert [m for m in msgs if m["type"] == "caption" and m["final"]][-1]["speaker"] == "Maya"
            ws.send_text('{"type":"end_visit"}')
            ws.send_text('{"type":"who"}')
            receive_until(ws, "who_answer")
    finally:
        backend_module.app.state.speechmatics_key = None
    [visit] = (Path(backend_module.app.state.data_dir) / "visits").glob("*.txt")
    text = visit.read_text()
    assert "Maya: Hi Grandma, visit 1." in text and "Someone:" not in text


def test_an_unknown_voice_is_nobody_even_with_a_user_registered(backend_client, backend_module, monkeypatch):
    """A voice that matches no one is not the wearer's: the wearer's own voice is enrolled like anyone's."""
    import backend.cloud_captions as cloud
    import backend.enroll_api as api

    monkeypatch.setattr(api, "trim_speech", lambda samples: samples)
    r = backend_client.post("/enroll", data={"name": "Rose", "relationship": "user"}, files=[("voice", ("v.wav", make_wav(4.0), "audio/wav"))])
    assert r.status_code == 201, r.text
    # The fake embedder's vectors are all close in cosine distance, so it can't produce a stranger: stub the matcher.
    monkeypatch.setattr("live.voices.VoiceIdentifier.identify", lambda self, samples: (None, "no_match", 0.9))
    monkeypatch.setattr(cloud, "RawLabelSession", lambda **kw: FakeSpeechmatics(**kw))
    backend_module.app.state.speechmatics_key = "test-key"
    try:
        with backend_client.websocket_connect("/live") as ws:
            for ts in (1, 2):  # two votes: enough to decide the label, and it matches nobody
                ws.send_text(json.dumps({"type": "audio", "ts": ts, "wav": b64(make_wav(3.0))}))
            captions = [m for _ in range(4) for m in receive_until(ws, "caption")]
            assert all(c["type"] == "caption" and c["speaker"] is None and c["person_id"] is None for c in captions), captions
            ws.send_text('{"type":"who"}')
            assert receive_until(ws, "who_answer")[-1]["text"] == "I don't see anyone I know right now."
    finally:
        backend_module.app.state.speechmatics_key = None


def test_local_captions_when_the_cloud_session_fails(backend_client, backend_module, monkeypatch):
    """A Speechmatics session that dies reports it once and the connection goes on with local captions."""
    import backend.cloud_captions as cloud

    class Broken(FakeSpeechmatics):
        async def run(self, audio, stop):
            raise ConnectionError("no route to speechmatics")

    monkeypatch.setattr(cloud, "RawLabelSession", lambda **kw: Broken(**kw))
    backend_module.app.state.speechmatics_key = "test-key"
    try:
        with backend_client.websocket_connect("/live") as ws:
            error = receive_until(ws, "error")[-1]
            assert "Live captions unavailable" in error["message"]
            ws.send_text(json.dumps({"type": "audio", "ts": 1, "wav": b64(make_wav(2.0))}))  # silence: handled locally, no caption
            ws.send_text('{"type":"who"}')
            assert [m["type"] for m in receive_until(ws, "who_answer")] == ["who_answer"]
    finally:
        backend_module.app.state.speechmatics_key = None


def test_nova_introduces_herself_again_after_a_visit_ends(backend_client, backend_module, monkeypatch):
    from backend.live_api import LiveSession
    from tests.helpers import FakeClaude

    monkeypatch.setattr(backend_module.app.state, "claude", FakeClaude("David is your grandson."))
    session = LiveSession(backend_module.app.state)
    intro = "I'm Nova, the helper in your glasses. David is your grandson."
    assert [m.text for m in session.ask_nova("Nova, who is David?", "Rose")] == [intro]
    assert [m.text for m in session.ask_nova("Nova, who is David?", "Rose")] == ["David is your grandson."]
    session.visit.add("Rose", None, "Nova, who is David?")
    session.end_visit()
    assert [m.text for m in session.ask_nova("Nova, who is David?", "Rose")] == [intro]


def test_novas_context_on_live_leaves_out_voices_nobody_enrolled(backend_client, backend_module, monkeypatch):
    from backend.live_api import LiveSession
    from tests.helpers import FakeClaude

    claude = FakeClaude("Maya is your granddaughter.")
    monkeypatch.setattr(backend_module.app.state, "claude", claude)
    session = LiveSession(backend_module.app.state)
    session.visit.add("Maya", 1, "I brought the photos.")
    session.visit.add("Someone", None, "Is this seat taken?")
    session.ask_nova("Nova, who is Maya?", "Rose")
    [call] = claude.calls
    prompt = call["messages"][0]["content"]
    assert "Maya: I brought the photos." in prompt and "Is this seat taken?" not in prompt


def test_a_named_face_keeps_its_name_through_an_unsure_frame(backend_client, monkeypatch, maya):
    """A turned head, or a stranger's sample as near as the person's own, makes the matcher unsure
    for a frame; the tag must not blink out for that."""
    from live.faces import FaceIdentifier

    real = FaceIdentifier.identify
    calls = []

    def flaky(self, face):
        calls.append(1)
        return real(self, face) if len(calls) == 1 else (None, "not_sure", 0.3)

    monkeypatch.setattr(FaceIdentifier, "identify", flaky)
    with backend_client.websocket_connect("/live") as ws:
        ws.send_text(frame())
        assert receive_until(ws, "present")[-1]["faces"][0]["state"] == "named"
        for ts in (2, 3):
            ws.send_text(frame(ts=ts))
            present = receive_until(ws, "present")[-1]
            assert present["faces"] == [{"box": {"x": 0, "y": 0, "width": 1, "height": 1}, "state": "named", "person_id": maya["id"]}]
    assert len(calls) == 3


def test_a_voice_label_is_judged_on_everything_it_said_recently():
    """Each attempt hears the label's whole recent speech, not just the newest 1.5 s."""
    import numpy as np

    from backend.cloud_captions import DbLabelNamer

    heard = []

    class Identifier:
        def identify(self, samples):
            heard.append(len(samples) / 16000)
            return None, "no_match", 0.9

    namer = DbLabelNamer(Identifier(), min_audio=1.5)
    second = np.zeros(16000, dtype=np.float32)
    namer.offer("S1", second)  # 1 s: not yet
    namer.offer("S1", second)  # 2 s: an attempt on all 2 s
    namer.offer("S1", second)  # 3 s: 1 s new, not yet
    namer.offer("S1", second)  # 4 s: an attempt on all 4 s
    for _ in range(8):
        namer.offer("S1", second)
    assert heard[:2] == [2.0, 4.0] and max(heard) <= 8.0  # never more than MAX_AUDIO

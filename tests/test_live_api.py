"""The /live WebSocket on the real backend, with the fake embedders (the same bytes always give
the same embedding, so a frame of an enrolled picture is a match)."""

import json
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
        assert arrived["via"] == "face" and arrived["text"] == "That's Maya, your granddaughter."
        ws.send_text('{"type":"who"}')
        assert ws.receive_json() == {"type": "who_answer", "text": "That's Maya, your granddaughter."}


def test_a_strange_face_is_unsure_and_the_room_is_empty(backend_client):
    with backend_client.websocket_connect("/live") as ws:
        ws.send_text(frame())
        [present] = receive_until(ws, "present")
        assert present["people"] == [] and present["faces"][0]["state"] == "unsure"
        ws.send_text('{"type":"who"}')
        assert ws.receive_json()["text"] == "I don't see anyone I know right now."


def test_a_bad_message_keeps_the_socket_open(backend_client):
    with backend_client.websocket_connect("/live") as ws:
        ws.send_text('{"type":"dance"}')
        assert ws.receive_json()["type"] == "error"
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
    assert all(c["speaker"] == "User" and c["person_id"] is None for c in captions)  # nobody is registered
    assert any(len(c["text"].split()) >= 3 for c in captions)
    assert all(c["end"] > c["start"] >= 0 for c in captions)

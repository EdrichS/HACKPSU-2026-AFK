"""The enrollment wizard's routes, with the contract's fake embedders."""

import io

import pytest
from PIL import Image

from contract.fakes import make_wav
from db.context import list_facts
from tests.helpers import png_bytes


def jpeg_bytes(width: int = 64, height: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 90, 60)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def speech_as_is(monkeypatch):
    """Silent test audio counts as speech here; the VAD is exercised with real speech elsewhere."""
    import backend.enroll_api as api

    monkeypatch.setattr(api, "trim_speech", lambda samples: samples)


def test_health(backend_client):
    r = backend_client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["face_model"] == "fake-face"


def test_check_photo_reports_the_face(backend_client):
    r = backend_client.post("/enroll/check/photo", files={"file": ("front.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "faces": 1, "box": {"x": 0, "y": 0, "width": 1, "height": 1}, "width": 64, "height": 64, "reason": ""}


def test_check_photo_without_a_face(backend_client, backend_module, monkeypatch):
    monkeypatch.setattr(backend_module.face_embedder, "detect_faces", lambda image: [])
    r = backend_client.post("/enroll/check/photo", files={"file": ("front.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 200 and r.json()["ok"] is False and "face" in r.json()["reason"]


def test_check_photo_rejects_a_non_image(backend_client):
    r = backend_client.post("/enroll/check/photo", files={"file": ("x.jpg", b"nope", "image/jpeg")})
    assert r.status_code == 422


def test_check_voice(backend_client, speech_as_is):
    r = backend_client.post("/enroll/check/voice", files={"file": ("v.wav", make_wav(10.0), "audio/wav")})
    assert r.json() == {"ok": True, "seconds": 10.0, "speech_seconds": 10.0, "reason": ""}
    r = backend_client.post("/enroll/check/voice", files={"file": ("v.wav", b"not a wav", "audio/wav")})
    assert r.json()["ok"] is False and "16 kHz" in r.json()["reason"]
    r = backend_client.post("/enroll/check/voice", files={"file": ("v.wav", make_wav(1.5), "audio/wav")})
    assert r.json()["ok"] is False and "seconds of speech" in r.json()["reason"]


def test_enroll_stores_everything_the_wizard_collects(backend_client, speech_as_is, conn, tmp_path):
    files = [
        ("photos", ("front.jpg", jpeg_bytes(), "image/jpeg")),
        ("photos", ("left.jpg", jpeg_bytes(70, 60), "image/jpeg")),
        ("photos", ("right.png", png_bytes(50, 50), "image/png")),
        ("voice", ("voice.wav", make_wav(10.0), "audio/wav")),
    ]
    notes = "Anita's daughter, your oldest grandchild. Studying nursing, in her final year."
    r = backend_client.post("/enroll", data={"name": "Maya", "relationship": "granddaughter", "notes": notes}, files=files)
    assert r.status_code == 201, r.text
    out = r.json()
    person = out["person"]
    assert (person["name"], person["relationship"], person["face_count"], person["has_voice"]) == ("Maya", "granddaughter", 3, True)
    assert person["small_context"] == notes
    assert len(out["photo_ids"]) == 3 and len(out["face_ids"]) == 3 and out["skipped_photos"] == []
    assert len(out["voice_sample_ids"]) == 3  # the whole recording and two 4-second slices
    assert out["facts"] == 2
    assert [f.source for f in list_facts(conn, person["id"])] == ["notes", "notes"]
    img = backend_client.get(f"/photos/{out['photo_ids'][0]}/image")  # the thank-you page's picture
    assert img.status_code == 200 and img.content == jpeg_bytes()
    assert len(list(tmp_path.rglob("*.jpg"))) == 2 and len(list(tmp_path.rglob("*.png"))) == 1
    assert len(list(tmp_path.rglob("*.wav"))) == 3


def test_enroll_refuses_a_duplicate_unless_merging(backend_client, speech_as_is):
    files = [("photos", ("f.jpg", jpeg_bytes(), "image/jpeg"))]
    assert backend_client.post("/enroll", data={"name": "Maya", "relationship": "granddaughter"}, files=files).status_code == 201
    r = backend_client.post("/enroll", data={"name": " maya", "relationship": "Granddaughter"}, files=files)
    assert r.status_code == 409 and "merge" in r.json()["detail"]
    r = backend_client.post("/enroll", data={"name": "Maya", "relationship": "granddaughter", "merge": "true"}, files=files)
    assert r.status_code == 201 and r.json()["person"]["face_count"] == 2


def test_enroll_needs_one_clear_face_when_photos_are_sent(backend_client, backend_module, monkeypatch, speech_as_is):
    monkeypatch.setattr(backend_module.face_embedder, "detect_faces", lambda image: [])
    r = backend_client.post("/enroll", data={"name": "Maya", "relationship": "granddaughter"}, files=[("photos", ("f.jpg", jpeg_bytes(), "image/jpeg"))])
    assert r.status_code == 422 and "clear face" in r.json()["detail"]
    assert backend_client.get("/people").json() == []  # nothing was stored


def test_enroll_rejects_a_short_recording(backend_client, speech_as_is, tmp_path):
    r = backend_client.post("/enroll", data={"name": "Maya", "relationship": "granddaughter"}, files=[("voice", ("v.wav", make_wav(2.0), "audio/wav"))])
    assert r.status_code == 422 and "seconds of speech" in r.json()["detail"]
    assert backend_client.get("/people").json() == [] and list(tmp_path.rglob("*")) == []


def test_enroll_rejects_bad_names(backend_client):
    r = backend_client.post("/enroll", data={"name": "x" * 81, "relationship": "son"})
    assert r.status_code == 422


def test_the_user_is_enrolled_with_relationship_user(backend_client, speech_as_is):
    assert backend_client.get("/user").status_code == 404
    r = backend_client.post("/enroll", data={"name": "Rose", "relationship": "user"}, files=[("voice", ("v.wav", make_wav(5.0), "audio/wav"))])
    assert r.status_code == 201 and r.json()["person"]["face_count"] == 0 and r.json()["person"]["has_voice"]
    user = backend_client.get("/user").json()
    assert (user["name"], user["relationship"]) == ("Rose", "user")


def test_nova_is_off_without_claude(backend_client, backend_module):
    backend_module.app.state.claude = None
    r = backend_client.post("/nova/ask", json={"question": "who is Maya?"})
    assert r.status_code == 503


def test_the_test_ui_is_served(backend_client):
    r = backend_client.get("/ui/")
    assert r.status_code == 200 and "Name Tags" in r.text and "/enroll/check/photo" in r.text
    assert backend_client.get("/ui/live.html").status_code == 200
    assert backend_client.get("/ui/common.js").status_code == 200
    assert backend_client.get("/", follow_redirects=False).headers["location"] == "/ui/"

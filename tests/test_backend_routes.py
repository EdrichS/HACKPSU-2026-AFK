import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from contract.embedders import Box, EmbedderSpec, FaceDetection
from contract.fakes import make_wav
from db.connect import EmbedderMismatch
from tests.helpers import vec


def test_non_image_upload_is_rejected(backend_client):
    r = backend_client.post("/photos", files={"file": ("p.png", b"not an image", "image/png")})
    assert r.status_code == 422


def test_rotated_phone_photo_is_stored_upright(backend_client, backend_module, monkeypatch):   # Review Focus 1
    def detect_ignoring_exif(image):                     # like face_recognition.load_image_file
        w, h = Image.open(io.BytesIO(image)).size
        return [FaceDetection(box=Box(x=0, y=0, width=w, height=h), embedding=vec(1.0, dims=128))]
    monkeypatch.setattr(backend_module.face_embedder, "detect_faces", detect_ignoring_exif)
    img, exif, buf = Image.new("RGB", (4, 3)), Image.Exif(), io.BytesIO()
    exif[0x0112] = 6                                     # EXIF orientation: rotate 90°
    img.save(buf, "JPEG", exif=exif)
    out = backend_client.post("/photos", files={"file": ("p.jpg", buf.getvalue(), "image/jpeg")}).json()
    assert (out["width"], out["height"]) == (3, 4)
    assert out["faces"][0]["box"] == {"x": 0, "y": 0, "width": 3, "height": 4}


def test_recording_twice_keeps_both_files(backend_client, tmp_path):
    pid = backend_client.post("/people", json={"name": "David", "relationship": "grandson"}).json()["id"]
    for _ in range(2):
        r = backend_client.post(f"/people/{pid}/voice", files={"file": ("v.wav", make_wav(10.0), "audio/wav")})
        assert r.status_code == 201
    assert len(list(tmp_path.rglob("*.wav"))) == 2


def test_removing_a_person_deletes_their_recordings(backend_client, tmp_path):
    pid = backend_client.post("/people", json={"name": "David", "relationship": "grandson"}).json()["id"]
    backend_client.post(f"/people/{pid}/voice", files={"file": ("v.wav", make_wav(10.0), "audio/wav")})
    assert backend_client.delete(f"/people/{pid}").status_code == 204
    assert list(tmp_path.rglob("*.wav")) == []


def test_backend_refuses_to_start_with_a_mismatched_embedder(backend_module, monkeypatch):
    bigger = EmbedderSpec(dimensions=512, metric="cosine", cutoff=0.75, model="bigger-voice")
    monkeypatch.setattr(backend_module.voice_embedder, "spec", bigger)
    with pytest.raises(EmbedderMismatch, match=r"vector\(192\)"):
        with TestClient(backend_module.app):
            pass

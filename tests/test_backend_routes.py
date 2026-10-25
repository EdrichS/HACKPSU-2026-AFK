import io
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from contract.embedders import Box, EmbedderSpec, FaceDetection
from contract.fakes import FakeFaceEmbedder, make_wav
from db.connect import EmbedderMismatch
from db.people import create_person
from enroll import store
from tests.helpers import PNG_1x1, vec

ASTRONAUT = Path(__file__).resolve().parents[1] / "facial-recognition-foundation-46999b" / "tests" / "fixtures" / "astronaut.jpg"


class Overlap:
    """Counts how many callers are inside `with` at the same moment."""

    def __init__(self):
        self._lock = threading.Lock()
        self.now = self.most = 0

    def __enter__(self):
        with self._lock:
            self.now += 1
            self.most = max(self.most, self.now)

    def __exit__(self, *exc):
        with self._lock:
            self.now -= 1


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
    samples = backend_client.get(f"/people/{pid}/voice").json()
    assert len(samples) >= 2  # each upload: the recording and its 4-second slices
    assert len(list(tmp_path.rglob("*.wav"))) == len(samples)  # one file per sample, nothing lost or orphaned


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


def test_face_detection_runs_one_request_at_a_time(backend_module, monkeypatch):
    # dlib's detector keeps the image it is scanning in one shared object and releases Python's
    # lock while it runs; uploads and /live frames arrive on different threads.
    calls = Overlap()

    class SlowFaces(FakeFaceEmbedder):
        def detect_faces(self, image):
            with calls:
                time.sleep(0.2)
                return super().detect_faces(image)

    monkeypatch.setattr("contract.fakes.FakeFaceEmbedder", SlowFaces)
    face, _ = backend_module.make_embedders()
    monkeypatch.setattr(backend_module, "face_embedder", face)
    with TestClient(backend_module.app) as client:
        def upload():
            assert client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).status_code == 201

        threads = [threading.Thread(target=upload) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert calls.most == 1


def test_backend_starts_on_a_database_filled_by_enroll(backend_module, conn, monkeypatch, tmp_path):
    # python -m enroll stores samples from the real models; a backend on other models refuses them.
    monkeypatch.setenv("NAMETAGS_EMBEDDERS", "real")
    try:
        from embedders.face import FaceRecEmbedder
        from facerec.enroll import ENROLL_JITTERS

        face, voice = backend_module.make_embedders()
    except (ImportError, FileNotFoundError) as e:
        pytest.skip(f"real models unavailable: {e}")
    photo = io.BytesIO()
    Image.open(ASTRONAUT).crop((0, 0, 512, 300)).save(photo, "JPEG")  # her face only: dlib also "finds" one lower down
    pid = create_person(conn, "Rose", "friend").id
    store.save_photo_of(conn, tmp_path, pid, photo.getvalue(), FaceRecEmbedder(num_jitters=ENROLL_JITTERS))
    conn.commit()
    monkeypatch.setattr(backend_module, "face_embedder", face)
    monkeypatch.setattr(backend_module, "voice_embedder", voice)
    with TestClient(backend_module.app) as client:
        assert [p["face_count"] for p in client.get("/people").json()] == [1]

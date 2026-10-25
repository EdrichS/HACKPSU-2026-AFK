"""DELETE /photos/{id}: a failed sign-up, or a shot with no face, leaves nothing behind."""

from tests.helpers import PNG_1x1


def test_deleting_a_photo_removes_its_faces_and_file(backend_client, tmp_path):
    pid = backend_client.post("/people", json={"name": "Maya", "relationship": "granddaughter"}).json()["id"]
    photo = backend_client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).json()
    backend_client.post(f"/faces/{photo['faces'][0]['face_id']}/assign", json={"person_id": pid})
    assert backend_client.get("/people").json()[0]["face_count"] == 1
    assert len(list(tmp_path.rglob("*.png"))) == 1
    assert backend_client.delete(f"/photos/{photo['photo_id']}").status_code == 204
    assert backend_client.get("/photos").json() == []
    assert backend_client.get("/people").json()[0]["face_count"] == 0
    assert list(tmp_path.rglob("*.png")) == []
    assert backend_client.delete(f"/photos/{photo['photo_id']}").status_code == 404
    assert backend_client.get(f"/photos/{photo['photo_id']}/image").status_code == 404


def test_deleting_a_person_takes_their_sign_up_photos_with_them(backend_client, backend_module):
    """A face left behind unlabelled would make the matcher unsure about the same person signing up again."""
    from pathlib import Path

    pid = backend_client.post("/people", json={"name": "Maya", "relationship": "granddaughter"}).json()["id"]
    photo = backend_client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).json()
    backend_client.post(f"/faces/{photo['faces'][0]['face_id']}/assign", json={"person_id": pid})
    stored = Path(backend_module.app.state.data_dir) / "photos"
    assert len(list(stored.glob("*"))) == 1
    assert backend_client.delete(f"/people/{pid}").status_code == 204
    assert backend_client.get("/photos").json() == []
    assert list(stored.glob("*")) == []


def test_a_recording_is_stored_with_its_slices(backend_client, backend_module, monkeypatch):
    """One long recording gives several samples, as /enroll does, so matching has several views of the voice."""
    import backend.enroll_api as api
    from contract.fakes import make_wav

    monkeypatch.setattr(api, "trim_speech", lambda samples: samples)  # silence would trim to nothing
    pid = backend_client.post("/people", json={"name": "Maya", "relationship": "granddaughter"}).json()["id"]
    r = backend_client.post(f"/people/{pid}/voice", files={"file": ("v.wav", make_wav(10.0), "audio/wav")})
    assert r.status_code == 201, r.text
    samples = backend_client.get(f"/people/{pid}/voice").json()
    assert len(samples) >= 3 and samples[0]["voice_sample_id"] == r.json()["voice_sample_id"]

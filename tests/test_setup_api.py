import io

import pytest
from PIL import Image

from contract.fakes import FakeFaceEmbedder, make_wav
from tests.helpers import PNG_1x1

# The contract: the mock and the real backend must both pass every test here.
pytestmark = pytest.mark.parametrize("app_module", ["mock", "backend"], indirect=True)


def add_person(client, name="David", relationship="grandson"):
    return client.post("/people", json={"name": name, "relationship": relationship}).json()["id"]


def upload_photo(client):
    return client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).json()


def upload_voice(client, pid):
    return client.post(f"/people/{pid}/voice", files={"file": ("v.wav", make_wav(10.0), "audio/wav")})


def test_create_and_list_person(client):
    r = client.post("/people", json={"name": "David", "relationship": "grandson"})
    assert r.status_code == 201
    assert client.get("/people").json() == [
        {"id": r.json()["id"], "name": "David", "relationship": "grandson",
         "face_count": 0, "has_voice": False, "small_context": ""}]


def test_photo_then_assign_counts_face(client):
    pid = add_person(client)
    photo = upload_photo(client)
    assert client.post(f"/faces/{photo['faces'][0]['face_id']}/assign",
                       json={"person_id": pid}).status_code == 204
    assert client.get("/people").json()[0]["face_count"] == 1


def test_photo_with_no_faces_is_ok(client, app_module, monkeypatch):     # Review Focus 1
    monkeypatch.setattr(app_module.face_embedder, "detect_faces", lambda image: [])
    r = client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")})
    assert r.status_code == 201 and r.json()["faces"] == []


def test_reassign_moves_face(client):                                   # Review Focus 3
    ana = add_person(client, "Ana", "daughter")
    ben = add_person(client, "Ben", "son")
    face_id = upload_photo(client)["faces"][0]["face_id"]
    assert client.post(f"/faces/{face_id}/assign", json={"person_id": ana}).status_code == 204
    assert client.post(f"/faces/{face_id}/assign", json={"person_id": ben}).status_code == 204
    assert {p["name"]: p["face_count"] for p in client.get("/people").json()} == {"Ana": 0, "Ben": 1}


def test_voice_rejects_wrong_format(client):                            # Review Focus 4
    pid = add_person(client)
    r = client.post(f"/people/{pid}/voice", files={"file": ("v.wav", b"not a wav", "audio/wav")})
    assert r.status_code == 422 and "16 kHz" in r.text


def test_voice_accepts_wav_and_sets_has_voice(client):
    pid = add_person(client)
    assert upload_voice(client, pid).status_code == 201
    assert client.get("/people").json()[0]["has_voice"] is True


def test_unknown_person_is_404(client):
    assert client.patch("/people/999", json={"name": "X"}).status_code == 404


def test_photos_survive_a_reload(client):
    up = client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).json()
    assert client.get("/photos").json() == [up]


def test_photo_image_is_served(client):
    photo_id = client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).json()["photo_id"]
    assert client.get(f"/photos/{photo_id}/image").content == PNG_1x1


def test_same_name_and_relationship_is_409(client):
    client.post("/people", json={"name": "David", "relationship": "grandson"})
    r = client.post("/people", json={"name": " david", "relationship": "Grandson"})
    assert r.status_code == 409


def test_unlabelling_a_face(client):
    pid = add_person(client)
    face_id = upload_photo(client)["faces"][0]["face_id"]
    assert client.post(f"/faces/{face_id}/assign", json={"person_id": pid}).status_code == 204
    assert client.post(f"/faces/{face_id}/assign", json={"person_id": None}).status_code == 204
    assert client.get("/people").json()[0]["face_count"] == 0


def test_one_person_once_per_photo_is_409(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module.face_embedder, "detect_faces",
                        lambda image: FakeFaceEmbedder().detect_faces(image) * 2)
    pid = add_person(client)
    faces = upload_photo(client)["faces"]
    assert client.post(f"/faces/{faces[0]['face_id']}/assign", json={"person_id": pid}).status_code == 204
    assert client.post(f"/faces/{faces[1]['face_id']}/assign", json={"person_id": pid}).status_code == 409


def test_recordings_can_be_listed_and_one_deleted(client):
    pid = add_person(client)
    first = upload_voice(client, pid)
    assert first.status_code == 201
    assert upload_voice(client, pid).status_code == 201
    recordings = client.get(f"/people/{pid}/voice").json()
    # The mock stores one sample per upload; the real backend also stores each 4-second slice.
    assert len(recordings) >= 2 and recordings[0]["voice_sample_id"] == first.json()["voice_sample_id"]
    sample = recordings[0]["voice_sample_id"]
    assert client.delete(f"/people/{pid}/voice/{sample}").status_code == 204
    assert len(client.get(f"/people/{pid}/voice").json()) == len(recordings) - 1
    assert client.delete(f"/people/{pid}/voice/{sample}").status_code == 404


def test_patch_rejects_an_overlong_name(client):
    pid = client.post("/people", json={"name": "David", "relationship": "grandson"}).json()["id"]
    assert client.patch(f"/people/{pid}", json={"name": "x" * 81}).status_code == 422


def test_phone_jpeg_with_a_second_image_is_accepted(client):
    # Ultra HDR and portrait photos from phones are JPEGs that carry a second image (Pillow: "MPO").
    buf = io.BytesIO()
    Image.new("RGB", (4, 3)).save(buf, "MPO", save_all=True, append_images=[Image.new("RGB", (4, 3))])
    r = client.post("/photos", files={"file": ("p.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 201
    assert (r.json()["width"], r.json()["height"]) == (4, 3)


def test_voice_rejects_a_too_short_recording(client):
    pid = add_person(client)
    r = client.post(f"/people/{pid}/voice", files={"file": ("v.wav", make_wav(0.5), "audio/wav")})
    assert r.status_code == 422 and "at least 1 second" in r.text
    assert client.get("/people").json()[0]["has_voice"] is False


def test_a_page_on_another_localhost_port_can_call_the_api(client):
    preflight = client.options("/people", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
    other_site = client.get("/people", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in other_site.headers

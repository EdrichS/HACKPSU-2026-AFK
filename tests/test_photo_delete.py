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

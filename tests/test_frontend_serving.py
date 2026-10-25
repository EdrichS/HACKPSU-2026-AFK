"""The API serves the built frontend at / and answers the frontend's /api/... calls."""

import json

from fastapi.testclient import TestClient

from tests.helpers import PNG_1x1, b64


def test_api_prefix_reaches_the_routes_over_http_and_websocket(backend_client):
    assert backend_client.get("/api/health").json()["status"] == "ok"
    assert backend_client.get("/api/people").json() == []
    r = backend_client.post("/api/people", json={"name": "Maya", "relationship": "granddaughter"})
    assert r.status_code == 201
    assert backend_client.get("/people").json()[0]["name"] == "Maya"  # the same routes, no prefix
    with backend_client.websocket_connect("/api/live") as ws:
        ws.send_text('{"type":"who"}')
        assert ws.receive_json()["type"] == "who_answer"
        ws.send_text(json.dumps({"type": "frame", "ts": 1, "jpeg": b64(PNG_1x1)}))
        assert ws.receive_json()["type"] == "present"


def test_built_frontend_is_served_with_history_fallback(backend_module, monkeypatch, tmp_path, test_db):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Name Tags</title><div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log('hi')")
    monkeypatch.setenv("NAMETAGS_FRONTEND_DIST", str(dist))
    monkeypatch.setenv("DATABASE_URL", test_db)
    with TestClient(backend_module.app) as client:
        for path in ("/", "/visitor", "/visitor/photos", "/setup/voice", "/live"):
            r = client.get(path)
            assert r.status_code == 200 and "Name Tags" in r.text, path
        r = client.get("/assets/app.js")
        assert r.status_code == 200 and r.text == "console.log('hi')"
        assert client.get("/health").json()["status"] == "ok"  # routes still win over the fallback
        assert client.get("/docs").status_code == 200
        assert client.get("/assets/../index.html").status_code == 200  # normalized, never escapes dist
        assert "Name Tags" in client.get("/assets/../index.html").text
        assert client.get("/").headers["cache-control"] == "no-cache"
        assert client.get("/assets/app.js").headers["cache-control"] == "public, max-age=31536000, immutable"
        r = client.get("/api/no-such-route")  # an API typo is a 404, never the app's page
        assert r.status_code == 404 and r.json()["detail"] == "Not Found"


def test_without_a_build_the_root_explains(backend_module, monkeypatch, tmp_path, test_db):
    monkeypatch.setenv("NAMETAGS_FRONTEND_DIST", str(tmp_path / "nowhere"))
    monkeypatch.setenv("DATABASE_URL", test_db)
    with TestClient(backend_module.app) as client:
        r = client.get("/")
        assert r.status_code == 404 and "npm run dev" in r.json()["detail"]

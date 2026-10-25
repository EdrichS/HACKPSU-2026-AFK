import os

import psycopg
import pytest
from fastapi.testclient import TestClient

# The backend loads the real face and voice models unless told otherwise; tests use the fakes.
os.environ.setdefault("NAMETAGS_EMBEDDERS", "fake")

from db.connect import DEFAULT_URL, apply_schema

TEST_URL = "postgresql://nametags:nametags@localhost:5433/nametags_test"


@pytest.fixture(scope="session")
def test_db():
    """A fresh nametags_test database. Not autouse: the contract tests run without Docker."""
    with psycopg.connect(DEFAULT_URL, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS nametags_test WITH (FORCE)")
        admin.execute("CREATE DATABASE nametags_test")
    with psycopg.connect(TEST_URL) as conn:
        apply_schema(conn)
    return TEST_URL


@pytest.fixture
def conn(test_db):
    c = psycopg.connect(TEST_URL)
    c.execute("TRUNCATE people, photos, face_samples, voice_samples, facts RESTART IDENTITY CASCADE")
    c.commit()
    yield c
    c.rollback()
    c.close()


@pytest.fixture
def backend_module(test_db, monkeypatch, tmp_path):
    """The real backend, pointed at an emptied nametags_test and a temporary data folder."""
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    monkeypatch.setenv("NAMETAGS_DATA", str(tmp_path))
    monkeypatch.setenv("NAMETAGS_CAPTIONS", "local")  # a Speechmatics key in .env must not send test audio anywhere
    # A real GEMINI_API_KEY in .env must not make the tests call Gemini: an empty value keeps
    # load_dotenv from filling it in, so Gemini is off unless a test fakes the client.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with psycopg.connect(TEST_URL) as c:
        c.execute("TRUNCATE people, photos, face_samples, voice_samples, facts RESTART IDENTITY CASCADE")
    import backend.app

    return backend.app


@pytest.fixture
def app_module(request):
    """The app module the route tests run against: the mock unless parametrized with "backend"."""
    if getattr(request, "param", "mock") == "backend":
        return request.getfixturevalue("backend_module")
    import mock.app

    mock.app.reset()
    return mock.app


@pytest.fixture
def client(app_module):
    with TestClient(app_module.app) as c:  # entering runs the app's lifespan
        yield c


@pytest.fixture
def backend_client(backend_module):
    with TestClient(backend_module.app) as c:
        yield c

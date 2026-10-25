import psycopg
import pytest
from fastapi.testclient import TestClient

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
def app_module():
    """The app module the route tests run against."""
    import mock.app

    mock.app.reset()
    return mock.app


@pytest.fixture
def client(app_module):
    with TestClient(app_module.app) as c:
        yield c

import pytest
from fastapi.testclient import TestClient


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

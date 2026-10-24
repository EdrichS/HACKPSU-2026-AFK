from pathlib import Path

import numpy as np
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
ASTRONAUT = FIXTURES / "astronaut.jpg"


def random_encoding(seed):
    """A unit-length 128-d vector; random pairs are ~1.4 apart, far beyond any tolerance."""
    vector = np.random.default_rng(seed).normal(size=128)
    return vector / np.linalg.norm(vector)


@pytest.fixture(scope="session")
def recognizer_factory():
    """Build real FaceRecognizers (loads dlib models once per session)."""
    from facerec import FaceConfig, FaceRecognizer

    def make(**config):
        return FaceRecognizer(config=FaceConfig(**config))

    return make


@pytest.fixture(scope="session")
def astronaut_rgb():
    from facerec import load_image

    return load_image(ASTRONAUT)


@pytest.fixture(scope="session")
def astronaut_face_rgb(astronaut_rgb):
    """Crop containing only her face (no mission patch), suitable for enrollment."""
    return np.ascontiguousarray(astronaut_rgb[:260, 80:380])

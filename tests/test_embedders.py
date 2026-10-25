import pytest

from contract.embedders import Box, FaceDetection, check_face_embedder, check_voice_embedder
from contract.fakes import FakeFaceEmbedder, FakeVoiceEmbedder, make_wav
from tests.helpers import PNG_1x1


def test_fake_face_embedder_passes_checker():
    check_face_embedder(FakeFaceEmbedder(), PNG_1x1)


def test_fake_voice_embedder_passes_checker():
    check_voice_embedder(FakeVoiceEmbedder(), make_wav())


def test_checker_rejects_wrong_dimensions():          # Review Focus 2
    class Short(FakeFaceEmbedder):
        def detect_faces(self, image):
            return [FaceDetection(box=Box(x=0, y=0, width=1, height=1), embedding=[0.0] * 127)]
    with pytest.raises(AssertionError, match="128"):
        check_face_embedder(Short(), PNG_1x1)


def test_fake_face_embedding_is_deterministic():
    f = FakeFaceEmbedder()
    assert f.detect_faces(PNG_1x1) == f.detect_faces(PNG_1x1)

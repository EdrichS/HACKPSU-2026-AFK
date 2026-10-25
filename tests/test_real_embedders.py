"""The real face and voice embedders meet the contract and fit the schema.

Skipped when their models aren't available: dlib not built, or the speaker model not downloaded
(hackpsu_voice_rec/scripts/download_models.sh).
"""

from pathlib import Path

import numpy as np
import pytest

from contract.embedders import check_face_embedder, check_voice_embedder
from db.connect import check_embedders

ROOT = Path(__file__).resolve().parents[1]
ASTRONAUT = ROOT / "facial-recognition-foundation-46999b" / "tests" / "fixtures" / "astronaut.jpg"


@pytest.fixture(scope="module")
def face():
    try:
        from embedders.face import FaceRecEmbedder

        return FaceRecEmbedder()
    except ImportError as e:
        pytest.skip(f"face embedder unavailable: {e}")


@pytest.fixture(scope="module")
def voice():
    from embedders.voice import VoiceRecEmbedder

    try:
        return VoiceRecEmbedder()
    except FileNotFoundError as e:
        pytest.skip(str(e))


def synthetic_voice(seconds: float = 3.0, pitch_hz: float = 120.0, seed: int = 0) -> bytes:
    """A buzzy vowel-like signal with a wobbling pitch and syllable-like loudness, as 16 kHz WAV."""
    from embedders.voice import encode_wav

    rate = 16000
    t = np.arange(int(seconds * rate)) / rate
    pitch = pitch_hz * (1 + 0.05 * np.sin(2 * np.pi * (0.5 + seed) * t))
    phase = 2 * np.pi * np.cumsum(pitch) / rate
    signal = sum(np.sin(k * phase) / k for k in range(1, 8))
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t) ** 2
    return encode_wav(0.3 * signal / np.max(np.abs(signal)) * envelope)


def test_face_embedder_finds_the_astronaut(face):
    data = ASTRONAUT.read_bytes()
    check_face_embedder(face, data)
    found = face.detect_faces(data)
    assert len(found) >= 1
    assert all(len(f.embedding) == 128 for f in found)
    assert (face.spec.dimensions, face.spec.metric) == (128, "l2")
    assert 0 < face.spec.cutoff <= 1


def test_face_boxes_fit_inside_the_image(face):
    from PIL import Image

    width, height = Image.open(ASTRONAUT).size
    for f in face.detect_faces(ASTRONAUT.read_bytes()):
        assert 0 <= f.box.x and 0 <= f.box.y
        assert f.box.x + f.box.width <= width and f.box.y + f.box.height <= height


def test_voice_embedder_meets_the_contract(voice):
    check_voice_embedder(voice, synthetic_voice())
    assert (voice.spec.dimensions, voice.spec.metric, voice.spec.model) == (192, "cosine", "nemo_en_titanet_small")
    assert 0 < voice.spec.cutoff < 1


def test_same_clip_embeds_the_same_and_another_differs(voice):
    a = np.array(voice.embed_voice(synthetic_voice(seed=0)))
    b = np.array(voice.embed_voice(synthetic_voice(seed=0)))
    c = np.array(voice.embed_voice(synthetic_voice(pitch_hz=220.0, seed=3)))
    assert np.allclose(a, b)
    assert float(a @ c) < 0.999  # cosine similarity: a different voice is not identical


def test_wav_roundtrip_and_resampling():
    from embedders.voice import decode_wav, encode_wav

    samples = (0.5 * np.sin(np.linspace(0, 200, 16000))).astype(np.float32)
    back = decode_wav(encode_wav(samples))
    assert back.shape == samples.shape and np.max(np.abs(back - samples)) < 1e-3
    eight_k = decode_wav(encode_wav(samples[:8000], sample_rate=8000))
    assert len(eight_k) == 16000  # a second of 8 kHz audio becomes a second of 16 kHz audio


def test_embedders_fit_the_schema(conn, face, voice):
    check_embedders(conn, face.spec, voice.spec)  # vector(128) and vector(192), empty tables

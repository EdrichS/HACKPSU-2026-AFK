"""Stand-in embedders, so every part can be built before the real models exist.

The spec values are placeholders; the real ones come from the face and voice owners.
"""

import hashlib
import io
import wave

from contract.embedders import Box, EmbedderSpec, FaceDetection


def _embedding(data: bytes, dimensions: int) -> list[float]:
    """Numbers in (0, 1] derived from `data`: deterministic, finite, never all zeros."""
    stream = b""
    counter = 0
    while len(stream) < dimensions:
        stream += hashlib.sha256(data + counter.to_bytes(4, "big")).digest()
        counter += 1
    return [(b + 1) / 256 for b in stream[:dimensions]]


class FakeFaceEmbedder:
    spec = EmbedderSpec(dimensions=128, metric="l2", cutoff=0.6, model="fake-face")

    def detect_faces(self, image: bytes) -> list[FaceDetection]:
        # A 1x1 box fits any image.
        return [FaceDetection(box=Box(x=0, y=0, width=1, height=1), embedding=_embedding(image, 128))]


class FakeVoiceEmbedder:
    spec = EmbedderSpec(dimensions=192, metric="cosine", cutoff=0.75, model="fake-voice")

    def embed_voice(self, wav: bytes) -> list[float]:
        return _embedding(wav, 192)


def make_wav(seconds: float = 1.0) -> bytes:
    """Silent 16 kHz mono 16-bit audio."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()

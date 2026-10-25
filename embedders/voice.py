"""The voice embedder for the contract, built on voice_rec (sherpa-onnx speaker models).

Implements contract.embedders.VoiceEmbedder: one embedding for a WAV clip. The default model,
NeMo TitaNet small, returns 192 numbers, which is what voice_samples.embedding vector(192) in
db/schema.sql holds. The backend swaps this in for contract.fakes.FakeVoiceEmbedder.
"""

import io
import wave
from pathlib import Path

import numpy as np

from contract.embedders import EmbedderSpec
from voice_rec.audio import resample
from voice_rec.config import DEFAULT_EMBED_MODEL, DEFAULT_THRESHOLD, SAMPLE_RATE
from voice_rec.embedder import SpeakerEmbedder


def decode_wav(data: bytes) -> np.ndarray:
    """WAV bytes -> float32 mono samples at 16 kHz. 16-bit PCM is the contract; 8 and 32-bit decode too."""
    with wave.open(io.BytesIO(data)) as w:
        channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(width)
    if dtype is None:
        raise ValueError(f"unsupported WAV sample width: {width * 8}-bit")
    samples = np.frombuffer(raw, dtype=dtype)
    if width == 1:
        samples = (samples.astype(np.float32) - 128.0) / 128.0
    else:
        samples = samples.astype(np.float32) / float(2 ** (width * 8 - 1))
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return resample(np.ascontiguousarray(samples, dtype=np.float32), rate, SAMPLE_RATE)


def encode_wav(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """float32 mono samples -> 16-bit PCM WAV bytes, the contract's format."""
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class VoiceRecEmbedder:
    def __init__(
        self,
        model_path: str = DEFAULT_EMBED_MODEL,
        threshold: float = DEFAULT_THRESHOLD,
        num_threads: int = 2,
    ):
        self.embedder = SpeakerEmbedder(model_path, num_threads=num_threads)
        self.spec = EmbedderSpec(
            dimensions=self.embedder.dim,
            metric="cosine",
            # voice_rec's threshold is a similarity; the contract wants a distance (1 - similarity).
            cutoff=round(1.0 - threshold, 4),
            model=Path(model_path).stem,
        )

    def embed_voice(self, wav: bytes) -> list[float]:
        """The embedding of a WAV clip (16 kHz, mono, 16-bit)."""
        return self.embed_samples(decode_wav(wav))

    def embed_samples(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> list[float]:
        """The same for float32 samples already in memory (a microphone buffer, say)."""
        return [float(x) for x in self.embedder.embed(samples, sample_rate)]

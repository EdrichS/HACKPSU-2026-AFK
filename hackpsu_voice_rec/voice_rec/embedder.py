"""Speaker-embedding extraction via sherpa-onnx (WeSpeaker / 3D-Speaker / NeMo ONNX models)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import sherpa_onnx

from .config import DEFAULT_EMBED_MODEL, SAMPLE_RATE

MIN_EMBED_SECONDS = 0.5


class SpeakerEmbedder:
    def __init__(self, model_path: str = DEFAULT_EMBED_MODEL, num_threads: int = 2):
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(model_path), num_threads=num_threads)
        if not cfg.validate():
            raise FileNotFoundError(
                f"Speaker model not found at {model_path}. Run scripts/download_models.sh."
            )
        self._ex = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        self.dim: int = self._ex.dim
        self.model_path = str(model_path)
        self.model_name = Path(model_path).name

    def embed(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
        """Return an L2-normalised embedding for one utterance."""
        samples = np.asarray(samples, dtype=np.float32)
        if len(samples) < MIN_EMBED_SECONDS * sample_rate:
            raise ValueError(
                f"Utterance too short ({len(samples)/sample_rate:.2f}s); need >= {MIN_EMBED_SECONDS}s"
            )
        stream = self._ex.create_stream()
        stream.accept_waveform(sample_rate=sample_rate, waveform=samples)
        stream.input_finished()
        if not self._ex.is_ready(stream):
            raise ValueError("Extractor not ready; utterance too short for this model")
        emb = np.asarray(self._ex.compute(stream), dtype=np.float32)
        norm = float(np.linalg.norm(emb))
        return emb / norm if norm > 0 else emb

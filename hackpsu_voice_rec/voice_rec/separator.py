"""Speech separation: split a mixture of simultaneous talkers into one stream per talker.

Uses SpeechBrain's SepFormer (default: the WHAMR! 16 kHz model, trained on noisy,
reverberant two-speaker mixtures, the closest public match to a laptop mic in a room).
PyTorch and SpeechBrain are optional dependencies: `pip install -e '.[separation]'`.
"""
from __future__ import annotations

import os
import time
import warnings

import numpy as np

from .config import MODELS_DIR, SAMPLE_RATE

DEFAULT_SEP_MODEL = os.environ.get("VOICEREC_SEP_MODEL", "speechbrain/sepformer-whamr16k")
TARGET_RMS = 0.05  # SepFormer is not level-invariant; feed it a consistent loudness


class SeparationUnavailable(RuntimeError):
    pass


class SpeechSeparator:
    def __init__(self, source: str = DEFAULT_SEP_MODEL, device: str | None = None, num_threads: int = 4):
        try:
            import torch
            from speechbrain.inference.separation import SepformerSeparation
        except ImportError as e:  # pragma: no cover
            raise SeparationUnavailable(
                "speech separation needs PyTorch + SpeechBrain: pip install -e '.[separation]'"
            ) from e
        torch.set_num_threads(num_threads)
        if device is None:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._torch = torch
        self.device = device
        self.source = source
        savedir = MODELS_DIR / source.split("/")[-1]
        t = time.time()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._model = SepformerSeparation.from_hparams(
                source=source, savedir=str(savedir), run_opts={"device": device}
            )
        self.load_seconds = time.time() - t
        self.num_sources: int | None = None  # learned from the first call

    def separate(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> list[np.ndarray]:
        """Return one float32 stream per (possible) talker, same length as the input."""
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"separator expects {SAMPLE_RATE} Hz audio")
        x = np.asarray(samples, dtype=np.float32)
        rms = float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0
        if rms > 0:
            x = x * (TARGET_RMS / rms)
        torch = self._torch
        with torch.no_grad():
            est = self._model.separate_batch(torch.from_numpy(x)[None].to(self.device))
        est = est.detach().cpu().numpy()[0]  # [time, n_sources]
        self.num_sources = est.shape[1]
        return [np.ascontiguousarray(est[:, i], dtype=np.float32) for i in range(est.shape[1])]

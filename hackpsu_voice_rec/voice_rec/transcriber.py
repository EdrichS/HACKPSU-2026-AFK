"""Speech-to-text for finished utterances, via sherpa-onnx offline recognizers.

Default model: Moonshine base (English, int8), small and built for short utterances on
CPU. A Whisper export from sherpa-onnx works too: point VOICEREC_ASR_MODEL at its folder.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import sherpa_onnx

from .config import MODELS_DIR, SAMPLE_RATE

DEFAULT_ASR_MODEL = os.environ.get("VOICEREC_ASR_MODEL", str(MODELS_DIR / "sherpa-onnx-moonshine-base-en-int8"))
MIN_SECONDS = 0.3


class Transcriber:
    def __init__(self, model_dir: str = DEFAULT_ASR_MODEL, num_threads: int = 2):
        d = Path(model_dir)
        if not d.is_dir():
            raise FileNotFoundError(f"speech-to-text model folder not found: {d}. Run scripts/download_models.sh")
        t = time.time()
        if (d / "preprocess.onnx").exists():  # Moonshine layout
            pick = lambda stem: str(next(iter(sorted(d.glob(f"{stem}*.onnx"))), d / f"{stem}.onnx"))  # noqa: E731
            self._rec = sherpa_onnx.OfflineRecognizer.from_moonshine(
                preprocessor=str(d / "preprocess.onnx"),
                encoder=pick("encode"),
                uncached_decoder=pick("uncached_decode"),
                cached_decoder=pick("cached_decode"),
                tokens=str(d / "tokens.txt"),
                num_threads=num_threads,
            )
            self.kind = "moonshine"
        else:  # Whisper layout: <name>-encoder.int8.onnx / <name>-decoder.int8.onnx / <name>-tokens.txt
            enc = sorted(d.glob("*encoder*.onnx"))
            dec = sorted(d.glob("*decoder*.onnx"))
            tok = sorted(d.glob("*tokens.txt"))
            if not (enc and dec and tok):
                raise FileNotFoundError(f"no Moonshine or Whisper model files in {d}")
            self._rec = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(enc[0]), decoder=str(dec[0]), tokens=str(tok[0]), num_threads=num_threads
            )
            self.kind = "whisper"
        self.model_dir = str(d)
        self.load_seconds = time.time() - t

    def transcribe(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
        samples = np.asarray(samples, dtype=np.float32)
        if len(samples) < MIN_SECONDS * sample_rate:
            return ""
        stream = self._rec.create_stream()
        stream.accept_waveform(sample_rate, samples)
        self._rec.decode_stream(stream)
        return stream.result.text.strip()

"""Voice activity detection: turns a stream of audio blocks into speech segments."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import sherpa_onnx

from .config import SAMPLE_RATE, VAD_MODEL


@dataclass
class SpeechSegment:
    start: float  # seconds since the stream started
    samples: np.ndarray  # float32 @ 16 kHz

    @property
    def duration(self) -> float:
        return len(self.samples) / SAMPLE_RATE


class SpeechSegmenter:
    """Wraps the Silero VAD so callers can push arbitrary-size blocks.

    Silero wants exactly 512-sample windows, so incoming audio is buffered and
    fed in window-sized pieces. Completed utterances come back from feed()/flush().
    """

    WINDOW = 512

    def __init__(
        self,
        model_path: str = VAD_MODEL,
        sample_rate: int = SAMPLE_RATE,
        threshold: float = 0.5,
        min_silence: float = 0.3,
        min_speech: float = 0.3,
        max_speech: float = 10.0,
        pre_roll: float = 0.25,
    ):
        silero = sherpa_onnx.SileroVadModelConfig(
            model=str(model_path),
            threshold=threshold,
            min_silence_duration=min_silence,
            min_speech_duration=min_speech,
            window_size=self.WINDOW,
            max_speech_duration=max_speech,
        )
        cfg = sherpa_onnx.VadModelConfig(silero_vad=silero, sample_rate=sample_rate)
        if not cfg.validate():
            raise FileNotFoundError(
                f"VAD model not found at {model_path}. Run scripts/download_models.sh."
            )
        self.sample_rate = sample_rate
        self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=120)
        self._pending = np.zeros(0, dtype=np.float32)
        self._fed = 0  # samples pushed into the VAD since construction
        self._base = 0  # value of _fed at the last reset(); the VAD's own clock restarts there
        # Silero starts a segment a little after speech really begins, which clips the first
        # word for transcription. Keep recent audio so `pre_roll` seconds can be put back.
        self._pre_roll = int(pre_roll * sample_rate)
        self._history_len = int((max_speech + 30) * sample_rate)
        self._history = np.zeros(0, dtype=np.float32)

    def feed(self, chunk: np.ndarray) -> list[SpeechSegment]:
        self._pending = np.concatenate([self._pending, np.asarray(chunk, dtype=np.float32)])
        n_full = (len(self._pending) // self.WINDOW) * self.WINDOW
        for i in range(0, n_full, self.WINDOW):
            self._vad.accept_waveform(self._pending[i : i + self.WINDOW])
        self._remember(self._pending[:n_full])
        self._fed += n_full
        self._pending = self._pending[n_full:]
        return self._drain()

    def _remember(self, x: np.ndarray) -> None:
        if self._pre_roll <= 0:
            return
        self._history = np.concatenate([self._history, x])[-self._history_len :]

    def _with_pre_roll(self, abs_start: int, samples: np.ndarray) -> np.ndarray:
        """Prepend up to pre_roll seconds of the audio heard just before abs_start."""
        if self._pre_roll <= 0:
            return samples
        hist_start = self._fed - len(self._history)  # absolute index of history[0]
        lo = max(abs_start - self._pre_roll, hist_start)
        hi = min(abs_start, self._fed)
        if hi <= lo:
            return samples
        return np.concatenate([self._history[lo - hist_start : hi - hist_start], samples])

    def flush(self) -> list[SpeechSegment]:
        """Force out whatever speech is in progress (end of file / Ctrl-C)."""
        if len(self._pending):
            pad = np.zeros(self.WINDOW - len(self._pending), dtype=np.float32)
            self._vad.accept_waveform(np.concatenate([self._pending, pad]))
            self._remember(self._pending)
            self._fed += self.WINDOW
            self._pending = np.zeros(0, dtype=np.float32)
        self._vad.flush()
        return self._drain()

    def _drain(self) -> list[SpeechSegment]:
        out = []
        while not self._vad.empty():
            seg = self._vad.front
            abs_start = self._base + seg.start
            samples = self._with_pre_roll(abs_start, np.asarray(seg.samples, dtype=np.float32))
            out.append(
                SpeechSegment(
                    start=max(0, abs_start - (len(samples) - len(seg.samples))) / self.sample_rate,
                    samples=samples,
                )
            )
            self._vad.pop()
        return out

    @property
    def is_speech(self) -> bool:
        return bool(self._vad.is_speech_detected())

    def _current(self):
        cur = self._vad.current_segment
        return cur() if callable(cur) else cur

    def current_speech(self) -> np.ndarray:
        """Audio of the utterance currently in progress (empty if silent), with pre-roll."""
        cur = self._current()
        samples = np.asarray(cur.samples, dtype=np.float32)
        if not len(samples):
            return samples
        return self._with_pre_roll(self._base + cur.start, samples)

    def current_start(self) -> float:
        """Start time (seconds since stream start) of the utterance in progress."""
        return (self._base + self._current().start) / self.sample_rate

    def reset(self) -> None:
        """Drop the utterance in progress and start fresh (timestamps stay continuous)."""
        self._vad.reset()
        self._base = self._fed
        self._pending = np.zeros(0, dtype=np.float32)
        # history is kept: the next segment may still want pre-roll from before the reset


def segment_audio(audio: np.ndarray, **kwargs) -> list[SpeechSegment]:
    """Run VAD over a whole clip. Falls back to the full clip if nothing is detected."""
    seg = SpeechSegmenter(**kwargs)
    out = seg.feed(audio)
    out += seg.flush()
    if not out:
        out = [SpeechSegment(start=0.0, samples=np.asarray(audio, dtype=np.float32))]
    return out

"""Microphone capture and audio file loading, all normalised to 16 kHz mono float32."""
from __future__ import annotations

import queue
import time
from typing import Iterator

import numpy as np

from .config import SAMPLE_RATE


def list_input_devices() -> list[dict]:
    import sounddevice as sd

    default_in = sd.default.device[0]
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append(
                {
                    "index": i,
                    "name": d["name"],
                    "default": i == default_in,
                    "default_samplerate": d["default_samplerate"],
                }
            )
    return out


def resolve_device(spec: str | int | None) -> int | None:
    """Accept a device index or a case-insensitive substring of its name."""
    if spec is None or spec == "":
        return None
    if isinstance(spec, int) or str(spec).isdigit():
        return int(spec)
    needle = str(spec).lower()
    for d in list_input_devices():
        if needle in d["name"].lower():
            return d["index"]
    raise ValueError(f"No input device matching {spec!r}. Run `voicerec devices` to list them.")


class Microphone:
    """Pulls mono float32 audio off an input device in fixed-size blocks.

    Audio arrives on PortAudio's callback thread and is handed over through a
    queue, so slow consumers (embedding computation) never drop samples.
    """

    def __init__(
        self,
        device: int | None = None,
        sample_rate: int = SAMPLE_RATE,
        block_size: int = 1024,
        latency: str | float = "high",
    ):
        self.device = device
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.latency = latency  # we buffer through a queue anyway; a deep device buffer survives CPU spikes
        self.overflows = 0
        self.started_at: float | None = None  # wall-clock time the stream started
        self._q: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if status and getattr(status, "input_overflow", False):
            self.overflows += 1
        self._q.put(indata[:, 0].copy())

    def __enter__(self) -> "Microphone":
        import sounddevice as sd

        self._stream = sd.InputStream(
            device=self.device,
            channels=1,
            samplerate=self.sample_rate,
            dtype="float32",
            blocksize=self.block_size,
            latency=self.latency,
            callback=self._callback,
        )
        self._stream.start()
        self.started_at = time.time()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def chunks(self, timeout: float = 1.0) -> Iterator[np.ndarray]:
        """Yield blocks forever; the caller breaks out or hits Ctrl-C."""
        while True:
            try:
                yield self._q.get(timeout=timeout)
            except queue.Empty:
                continue

    def pending(self) -> list[np.ndarray]:
        """The blocks that have arrived since the last call, without waiting (for GUI loops)."""
        out = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                return out


def rms(x: np.ndarray) -> float:
    if len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Linear-interpolation resampler with an anti-alias low-pass when downsampling.

    Good enough for speaker embeddings; avoids pulling in scipy/soxr.
    """
    if sr_in == sr_out:
        return x.astype(np.float32, copy=False)
    if sr_in > sr_out:
        cutoff = 0.45 * sr_out / sr_in  # as a fraction of sr_in
        taps = 63
        n = np.arange(taps) - (taps - 1) / 2
        h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.hamming(taps)
        h /= h.sum()
        x = np.convolve(x, h, mode="same")
    n_out = int(round(len(x) * sr_out / sr_in))
    t_in = np.arange(len(x)) / sr_in
    t_out = np.arange(n_out) / sr_out
    return np.interp(t_out, t_in, x).astype(np.float32)


def to_mono_16k(data: np.ndarray, sr: int) -> np.ndarray:
    if data.ndim == 2:
        data = data.mean(axis=1)
    data = data.astype(np.float32, copy=False)
    return resample(data, sr, SAMPLE_RATE)


def load_audio(path) -> np.ndarray:
    """Read any file soundfile understands (wav/flac/ogg/...) as 16 kHz mono float32."""
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    return to_mono_16k(data, sr)

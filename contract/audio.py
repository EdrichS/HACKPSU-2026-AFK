"""The one audio format the contract accepts: WAV, 16 kHz, mono, 16-bit, at least a second long."""

import io
import wave

WAV_FORMAT_MESSAGE = "Voice recordings must be WAV, 16 kHz, mono, 16-bit."
MIN_SECONDS = 1.0


def check_wav(data: bytes) -> None:
    """Raise ValueError unless `data` is a WAV in the contract's format and long enough to embed."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            ok = (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
            seconds = w.getnframes() / w.getframerate() if ok else 0.0
    except (wave.Error, EOFError):
        ok = False
    if not ok:
        raise ValueError(WAV_FORMAT_MESSAGE)
    if seconds < MIN_SECONDS:
        # A tap-and-release on Record would otherwise become a "voice profile" of nothing.
        raise ValueError("Voice recordings must be at least 1 second long.")

"""The one audio format the contract accepts: WAV, 16 kHz, mono, 16-bit."""

import io
import wave

WAV_FORMAT_MESSAGE = "Voice recordings must be WAV, 16 kHz, mono, 16-bit."


def check_wav(data: bytes) -> None:
    """Raise ValueError unless `data` is a WAV in the contract's format."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            ok = (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
    except (wave.Error, EOFError):
        ok = False
    if not ok:
        raise ValueError(WAV_FORMAT_MESSAGE)

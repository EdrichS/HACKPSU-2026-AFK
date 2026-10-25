"""Recording a voice sample: speech only (Silero VAD), until enough seconds of it are in hand."""

import time

import numpy as np

from voice_rec.audio import Microphone, load_audio, resolve_device, rms
from voice_rec.config import SAMPLE_RATE
from voice_rec.vad import SpeechSegmenter, segment_audio

# The Rainbow Passage: the phonetically balanced reading text speech research uses. The words
# matter far less than the amount of speech and the recording conditions.
PASSAGE = (
    "Hi, my name is {name}. When the sunlight strikes raindrops in the air, they act as a prism "
    "and form a rainbow. The rainbow is a division of white light into many beautiful colors. "
    "These take the shape of a long round arch, with its path high above, and its two ends "
    "apparently beyond the horizon. There is, according to legend, a boiling pot of gold at one "
    "end. People look, but no one ever finds it."
)
TIPS = (
    "Sit where you will sit during the demo, at the same distance from the laptop. After the "
    "passage, keep talking naturally until the bar fills."
)

MIN_UTTERANCE = 0.8  # seconds; shorter bursts are coughs and clicks
MIN_TOTAL = 3.0  # seconds of speech below which a recording is not worth keeping


class SpeechRecorder:
    """Collects speech from the microphone a block at a time, for a UI loop to drive.

    Enter it (that opens the microphone) and call poll() often. The level meter works at once;
    speech starts counting after start(). `done` turns True once `seconds` of speech are in hand,
    and finish() returns that speech as float32 at 16 kHz with the silences cut out.
    """

    def __init__(self, seconds: float, device=None, mic=None):
        self.seconds = seconds
        self.mic = mic if mic is not None else Microphone(resolve_device(device))
        self.segmenter = SpeechSegmenter(min_silence=0.4, max_speech=8.0)
        self.utterances: list[np.ndarray] = []
        self.total = 0.0  # seconds of finished utterances
        self.level = 0.0  # RMS of the latest block
        self.armed = False

    def __enter__(self) -> "SpeechRecorder":
        self.mic.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self.mic.__exit__(*exc)

    def start(self) -> None:
        self.armed = True

    def poll(self) -> None:
        for chunk in self.mic.pending():
            self.level = rms(chunk)
            if self.armed:
                self._take(self.segmenter.feed(chunk))

    def _take(self, segments) -> None:
        for s in segments:
            if s.duration >= MIN_UTTERANCE:
                self.utterances.append(s.samples)
                self.total += s.duration

    @property
    def speaking(self) -> bool:
        return self.armed and self.segmenter.is_speech

    @property
    def live(self) -> float:
        """Seconds of the utterance in progress."""
        return len(self.segmenter.current_speech()) / SAMPLE_RATE if self.armed else 0.0

    @property
    def progress(self) -> float:
        return min(1.0, (self.total + self.live) / self.seconds)

    @property
    def done(self) -> bool:
        return self.total >= self.seconds

    def finish(self) -> np.ndarray:
        self._take(self.segmenter.flush())
        if not self.utterances:
            raise ValueError("no speech detected")
        return np.concatenate(self.utterances)


def record_speech(seconds: float, device=None, show=None) -> np.ndarray:
    """Listen until `seconds` of speech have been heard (silence doesn't count); the terminal version.

    `show(progress, speaking, level)` is called a few times a second for a progress display.
    Ctrl-C stops early; with less than MIN_TOTAL seconds in hand that raises ValueError.
    """
    with SpeechRecorder(seconds, device) as recorder:
        recorder.start()
        try:
            while not recorder.done:
                recorder.poll()
                if show is not None:
                    show(recorder.progress, recorder.speaking, recorder.level)
                time.sleep(0.03)
        except KeyboardInterrupt:
            if recorder.total < MIN_TOTAL:
                raise ValueError(f"stopped with only {recorder.total:.1f}s of speech; nothing saved") from None
        return recorder.finish()


def speech_from_file(path) -> np.ndarray:
    """The speech in an audio file (anything soundfile reads), silences cut out, float32 at 16 kHz."""
    audio = load_audio(path)
    segments = [s for s in segment_audio(audio) if s.duration >= MIN_UTTERANCE]
    if not segments:
        raise ValueError(f"{path}: no speech found")
    return np.concatenate([s.samples for s in segments])


def windows(samples: np.ndarray, seconds: float) -> list[np.ndarray]:
    """Non-overlapping windows of `seconds`; a shorter tail is dropped."""
    n = int(seconds * SAMPLE_RATE)
    if n <= 0 or len(samples) < n:
        return []
    return [samples[i : i + n] for i in range(0, len(samples) - n + 1, n)]

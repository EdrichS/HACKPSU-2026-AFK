"""The pop-up window helpers and the recorder's bookkeeping, without a camera or a microphone."""

import numpy as np
import pytest

from enroll import ui
from enroll.mic import SpeechRecorder

TEXT = ("the quick brown fox jumps over the lazy dog " * 5).strip()


def test_wrap_keeps_every_line_within_the_width():
    lines = ui.wrap(TEXT, 300, 0.6)
    assert len(lines) > 1
    assert all(ui.text_width(line, 0.6) <= 300 for line in lines)
    assert " ".join(lines) == TEXT


def test_wrap_never_splits_a_word():
    assert ui.wrap("supercalifragilistic", 10) == ["supercalifragilistic"]


def test_fit_shrinks_wide_frames_only():
    assert ui.fit(np.zeros((480, 640, 3), np.uint8), 1280)[1] == 1.0
    shrunk, scale = ui.fit(np.zeros((1080, 1920, 3), np.uint8), 1280)
    assert shrunk.shape[:2] == (720, 1280)
    assert abs(scale - 2 / 3) < 1e-9


def test_level_fraction_runs_from_silence_to_full_scale():
    assert ui.level_fraction(0.0) == 0.0
    assert ui.level_fraction(1.0) == 1.0
    assert 0.0 < ui.level_fraction(0.01) < 1.0


def test_camera_render_draws_without_a_window():
    from enroll.camera import render

    frame = np.zeros((720, 1280, 3), np.uint8)
    thumbs = [np.zeros((90, 160, 3), np.uint8)]
    shown, (center, radius) = render(frame, [(100, 400, 300, 200)], 0, "Look at the camera", 0.5, "front", 0, 1, thumbs)
    assert shown.shape == frame.shape and radius > 0
    assert 0 <= center[0] < shown.shape[1] and 0 <= center[1] < shown.shape[0]
    assert shown.any()  # something was drawn


def test_voice_window_draws_without_a_window():
    from enroll.voice_window import HEIGHT, WIDTH, _draw

    class Still:
        seconds, total, live, level, armed, speaking, progress = 10.0, 2.5, 0.5, 0.05, True, True, 0.3

    canvas = _draw("David", Still(), "a notice")
    assert canvas.shape == (HEIGHT, WIDTH, 3)
    assert canvas.any()


class FakeMic:
    def __init__(self, blocks):
        self.blocks = list(blocks)
        self.open = False

    def __enter__(self):
        self.open = True
        return self

    def __exit__(self, *exc):
        self.open = False

    def pending(self):
        blocks, self.blocks = self.blocks, []
        return blocks


def test_recorder_meters_before_start_and_only_counts_speech_after():
    steady = np.full(1024, 0.3, np.float32)  # loud, but not speech
    mic = FakeMic([steady])
    try:
        recorder = SpeechRecorder(5.0, mic=mic)
    except FileNotFoundError as e:  # the VAD model isn't downloaded
        pytest.skip(str(e))
    with recorder:
        assert mic.open
        recorder.poll()
        assert recorder.level > 0 and recorder.total == 0 and not recorder.armed and recorder.progress == 0
        recorder.start()
        mic.blocks = [np.zeros(1024, np.float32)] * 20
        recorder.poll()
        assert recorder.armed and recorder.total == 0 and not recorder.done and not recorder.speaking
        with pytest.raises(ValueError, match="no speech"):
            recorder.finish()
    assert not mic.open

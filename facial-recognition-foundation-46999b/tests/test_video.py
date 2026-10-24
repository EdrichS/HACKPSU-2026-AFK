"""Live/capture loops with a fake camera and a fake recognizer (no dlib, no windows)."""

from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import facerec.video as video
from facerec import FaceConfig, FaceDatabase, RecognizedFace
from facerec.enroll import database_is_stale, photos_fingerprint


class FakeCapture:
    def __init__(self, frames):
        self.frames = list(frames)
        self.released = False

    def read(self):
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def release(self):
        self.released = True


class FakeRecognizer:
    """Finds one face in the middle of every frame."""

    def __init__(self, database=None, **config):
        self.config = FaceConfig(**config)
        self.database = database if database is not None else FaceDatabase()

    def _box(self, frame):
        h, w = frame.shape[:2]
        return (h // 4, 3 * w // 4, 3 * h // 4, w // 4)

    def identify_bgr_frame(self, frame):
        return [RecognizedFace(self._box(frame), "alice", 0.3, 0.9, np.zeros(128))]

    def locate_in_bgr_frame(self, frame):
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), [self._box(frame)]

    def encode(self, rgb, locations, num_jitters=None):
        rng = np.random.default_rng(len(self.database))
        return [rng.normal(size=128) for _ in locations]


@pytest.fixture
def camera(monkeypatch):
    capture = FakeCapture([np.zeros((120, 160, 3), np.uint8) for _ in range(5)])
    monkeypatch.setattr(video, "open_capture", lambda source: capture)
    monkeypatch.setattr(video, "_show", lambda frame: True)
    monkeypatch.setattr(video.cv2, "destroyAllWindows", lambda: None)
    return capture


def test_run_live_gives_callback_clean_frames(camera):
    received = []
    frames = video.run_live(FakeRecognizer(process_every_n_frames=2), display=True, on_faces=lambda faces, frame: received.append(frame))
    assert frames == 5
    assert len(received) == 3  # frames 0, 2, 4
    assert all(not frame.any() for frame in received), "boxes/fps text must not be drawn onto the callback's frame"
    assert camera.released


def test_show_handles_window_closed_on_qt(monkeypatch):
    monkeypatch.setattr(video.cv2, "imshow", lambda *a: None)
    monkeypatch.setattr(video.cv2, "waitKey", lambda *a: -1)

    def closed(*args):
        raise cv2.error("NULL window")

    monkeypatch.setattr(video.cv2, "getWindowProperty", closed)
    assert video._show(np.zeros((2, 2, 3), np.uint8)) is False


def test_capture_enrollment_saves_photos_and_stays_fresh(camera, tmp_path):
    faces_dir = tmp_path / "faces"
    db_path = tmp_path / "db.npz"
    recognizer = FakeRecognizer(FaceDatabase(source=photos_fingerprint(faces_dir)))

    saved = video.capture_enrollment(recognizer, "Bob", faces_dir, samples=3, interval=0, display=False)

    assert [p.parent.name for p in saved] == ["Bob"] * 3
    assert all(p.exists() for p in saved)
    assert recognizer.database.counts() == {"Bob": 3}
    recognizer.database.save(db_path)
    assert not database_is_stale(faces_dir, db_path)  # no needless rebuild next run


def test_capture_enrollment_rejects_bad_name_before_opening_camera(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "open_capture", lambda source: pytest.fail("camera opened"))
    with pytest.raises(ValueError):
        video.capture_enrollment(FakeRecognizer(), "../evil", tmp_path)


def test_parse_source():
    assert video.parse_source("0") == 0
    assert video.parse_source(2) == 2
    assert video.parse_source("clip.mp4") == "clip.mp4"
    assert video.parse_source("rtsp://cam/1") == "rtsp://cam/1"


def test_capture_enrollment_leaves_db_stale_if_folder_changed_meanwhile(monkeypatch, tmp_path):
    faces_dir = tmp_path / "faces"
    faces_dir.mkdir()
    db_path = tmp_path / "db.npz"

    class CaptureThatAddsAPhoto(FakeCapture):
        def read(self):
            if len(self.frames) == 5:  # someone drops a photo in while we capture
                (faces_dir / "zoe.jpg").write_bytes(b"z")
            return super().read()

    monkeypatch.setattr(video, "open_capture", lambda source: CaptureThatAddsAPhoto([np.zeros((120, 160, 3), np.uint8)] * 5))
    recognizer = FakeRecognizer(FaceDatabase(source=photos_fingerprint(faces_dir)))
    video.capture_enrollment(recognizer, "Bob", faces_dir, samples=2, interval=0, display=False)
    recognizer.database.save(db_path)
    assert database_is_stale(faces_dir, db_path)  # zoe.jpg was never encoded

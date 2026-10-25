"""Guided webcam capture: one photo per head pose, taken when a face is clearly in view."""

import time
from dataclasses import dataclass

import cv2
import numpy as np

from enroll import ui
from facerec.enroll import pick_enrollment_face
from facerec.video import open_capture

POSES = {
    "front": "Look straight at the camera",
    "left": "Turn your head a little to the LEFT, both eyes still in view",
    "right": "Turn your head a little to the RIGHT, both eyes still in view",
    "up": "Tilt your head UP a little",
    "down": "Tilt your head DOWN a little",
}
DEFAULT_POSES = list(POSES)
WINDOW = "Nametags enrollment: photos"
MAX_WIDTH = 1280  # the preview is shrunk to this; the saved photo keeps the camera's full size
BUTTON_RADIUS = 36
THUMB_HEIGHT = 90
QUIT, SKIP, TAKE = "quit", "skip", "take"


@dataclass
class Shot:
    pose: str
    jpeg: bytes
    forced: bool  # taken with the button or the space bar, whether or not a face was in view


def capture_poses(
    recognizer,
    poses=DEFAULT_POSES,
    shots_per_pose: int = 1,
    source=0,
    grace: float = 1.5,
    hold: float = 1.0,
    timeout: float = 30.0,
    display: bool = True,
    say=print,
    jpeg_quality: int = 92,
) -> list[Shot]:
    """Take `shots_per_pose` photos for each pose, in order, in a pop-up preview window.

    After each prompt the person gets `grace` seconds to move, then a photo is taken once one
    face has stayed in view for `hold` seconds. Clicking the shutter button or pressing space
    takes it now, s skips the pose and q (or closing the window) stops. A pose with no face in
    view for `timeout` seconds is skipped. `recognizer` is a facerec.FaceRecognizer; it only
    finds faces in the preview here. The photos come back as JPEG bytes of the full, unmirrored
    frame.
    """
    capture = open_capture(source)
    preview = _Preview() if display else None
    shots: list[Shot] = []
    try:
        for _ in range(10):  # the first frames from many webcams are dark
            capture.read()
        for pose in poses:
            prompt = POSES.get(pose, pose)
            for n in range(shots_per_pose):
                say(f"  {pose}: {prompt}")
                result = _capture_one(
                    capture, recognizer, preview, pose, prompt, n, shots_per_pose, grace, hold, timeout, jpeg_quality
                )
                if result == QUIT:
                    say("  stopped")
                    return shots
                if result is None:
                    say(f"  {pose}: skipped")
                    break
                shots.append(result)
                say(f"  {pose}: photo taken" + (" on request" if result.forced else ""))
    finally:
        capture.release()
        if preview is not None:
            preview.close()
    return shots


def _capture_one(capture, recognizer, preview, pose, prompt, index, total, grace, hold, timeout, quality):
    started = time.monotonic()
    face_since = None
    while True:
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError("the camera stopped sending frames")
        _, locations = recognizer.locate_in_bgr_frame(frame)
        chosen = pick_enrollment_face(locations)
        now = time.monotonic()
        ready = now - started >= grace
        if chosen is None or not ready:
            face_since = None
        elif face_since is None:
            face_since = now
        if not ready:
            progress = -1.0
        elif face_since is None:
            progress = 0.0
        else:
            progress = (now - face_since) / hold
        action = preview.show(frame, locations, chosen, prompt, progress, pose, index, total) if preview else None
        if action == QUIT:
            return QUIT
        if action == SKIP:
            return None
        if action == TAKE or progress >= 1.0:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                raise RuntimeError("could not encode the frame as JPEG")
            if preview is not None:
                preview.took(frame)
            return Shot(pose=pose, jpeg=buf.tobytes(), forced=action == TAKE)
        if now - started > timeout:
            return None


class _Preview:
    """The pop-up window: shows frames, collects keys and clicks, keeps thumbnails of the shots."""

    def __init__(self):
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        self.clicks = ui.Clicks(WINDOW)
        self.thumbs: list[np.ndarray] = []

    def show(self, frame, locations, chosen, prompt, progress, pose, index, total):
        shown, (center, radius) = render(frame, locations, chosen, prompt, progress, pose, index, total, self.thumbs)
        cv2.imshow(WINDOW, shown)
        key = cv2.waitKey(1) & 0xFF
        if ui.closed(WINDOW) or key in (ord("q"), 27):
            return QUIT
        if key == ord("s"):
            return SKIP
        if key == ord(" ") or any(ui.inside(center, radius, p) for p in self.clicks.take()):
            return TAKE
        return None

    def took(self, frame) -> None:
        """A white flash, and a thumbnail of the photo for the strip down the right edge."""
        shown, _ = ui.fit(frame, MAX_WIDTH)
        cv2.imshow(WINDOW, np.full_like(shown, 255))
        cv2.waitKey(90)
        height, width = frame.shape[:2]
        size = (int(width * THUMB_HEIGHT / height), THUMB_HEIGHT)
        self.thumbs.append(cv2.resize(cv2.flip(frame, 1), size, interpolation=cv2.INTER_AREA))

    def close(self) -> None:
        ui.close(WINDOW)


def render(frame, locations, chosen, prompt, progress, pose, index, total, thumbs):
    """Draw the mirrored preview: boxes, hints, thumbnails, shutter. Returns (image, (button center, radius))."""
    shown, scale = ui.fit(cv2.flip(frame, 1), MAX_WIDTH)  # a mirror feels natural to move in
    height, width = shown.shape[:2]
    frame_width = frame.shape[1]
    for i, (top, right, bottom, left) in enumerate(locations):
        x1, x2 = int((frame_width - right) * scale), int((frame_width - left) * scale)
        y1, y2 = int(top * scale), int(bottom * scale)
        cv2.rectangle(shown, (x1, y1), (x2, y2), ui.GREEN if i == chosen else ui.RED, 2)
    if not locations:
        hint = "no face in view"
    elif chosen is None:
        hint = "one person at a time, please"
    elif progress < 0:
        hint = "get ready..."
    elif progress < 1:
        done = int(progress * 20)
        hint = "hold still  " + "#" * done + "." * (20 - done)
    else:
        hint = "taking the photo"
    ui.text(shown, prompt, (16, 40), 0.85, thickness=2)
    ui.text(shown, f"{pose}  {index + 1}/{total}    {hint}", (16, 76), 0.65)

    y = 100
    for thumb in thumbs:
        th, tw = thumb.shape[:2]
        x = width - tw - 16
        if y + th > height - 130:
            break
        shown[y : y + th, x : x + tw] = thumb
        cv2.rectangle(shown, (x, y), (x + tw, y + th), ui.WHITE, 1)
        y += th + 8

    center = (width // 2, height - 72)
    ui.round_button(shown, center, BUTTON_RADIUS, ui.WHITE if chosen is not None else ui.GREY)
    ui.text(shown, "click the button or press space to take the photo now     s: skip this pose     q: stop", (16, height - 14), 0.5)
    return shown, (center, BUTTON_RADIUS)

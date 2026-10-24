"""Live recognition and webcam enrollment loops (OpenCV)."""

import logging
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .enroll import ENROLL_JITTERS, photos_fingerprint, pick_enrollment_face, validate_person_name
from .imaging import KNOWN_COLOR, UNKNOWN_COLOR, draw_faces, save_bgr

logger = logging.getLogger(__name__)

WINDOW_NAME = "facerec (q to quit)"
QUIT_KEYS = {ord("q"), 27}  # q, Esc


def parse_source(source):
    """'0' -> camera index 0; anything else (file path, RTSP/HTTP URL) is passed through."""
    if isinstance(source, int):
        return source
    return int(source) if str(source).isdigit() else str(source)


def open_capture(source=0):
    source = parse_source(source)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        hint = ""
        if isinstance(source, int):
            hint = (
                " Check that the camera is connected, not in use by another app (Zoom, browser),"
                " and that you have permission to use it (Linux: user in the 'video' group;"
                " macOS: allow camera access for your terminal)."
            )
        raise RuntimeError(f"could not open video source {source!r}.{hint}")
    return capture


class _FpsMeter:
    def __init__(self, smoothing=0.9):
        self.fps = 0.0
        self._smoothing = smoothing
        self._last = None

    def tick(self):
        now = time.perf_counter()
        if self._last is not None and now > self._last:
            instant = 1.0 / (now - self._last)
            self.fps = instant if self.fps == 0 else self._smoothing * self.fps + (1 - self._smoothing) * instant
        self._last = now


def _show(frame):
    """Display a frame. Returns False when the user pressed q/Esc or closed the window."""
    cv2.imshow(WINDOW_NAME, frame)
    key = cv2.waitKey(1) & 0xFF
    if key in QUIT_KEYS:
        return False
    try:
        return cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:  # the Qt backend raises once the window was closed with its X button
        return False


def run_live(recognizer, source=0, display=True, on_faces=None, max_frames=None):
    """Recognize faces from a camera or video until q/Esc, end of video or `max_frames`.

    Recognition runs on every Nth frame (config.process_every_n_frames); frames
    in between reuse the last result so the video stays smooth.

    on_faces(faces, bgr_frame) is called after each recognition pass, with a
    list of RecognizedFace (possibly empty) and the raw, un-annotated frame.
    It's the hook for app logic (unlock, greet, log attendance, fuse with voice
    ID, ...). Raise from it to stop the loop. Returns the number of frames read.
    """
    capture = open_capture(source)
    every_n = recognizer.config.process_every_n_frames
    fps = _FpsMeter()
    faces = []
    last_names = None
    frames = 0
    try:
        while max_frames is None or frames < max_frames:
            ok, frame = capture.read()
            if not ok:
                logger.info("video source %r ended after %d frame(s)", source, frames)
                break
            if frames % every_n == 0:
                faces = recognizer.identify_bgr_frame(frame)
                if on_faces is not None:
                    on_faces(faces, frame)
                names = sorted(face.name for face in faces)
                if names != last_names:
                    logger.info("faces: %s", ", ".join(names) if names else "(none)")
                    last_names = names
            frames += 1
            fps.tick()
            if display:
                shown = draw_faces(frame.copy(), faces)  # keep `frame` clean for on_faces consumers
                cv2.putText(shown, f"{fps.fps:4.1f} fps", (10, 25), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)
                if not _show(shown):
                    break
    finally:
        capture.release()
        if display:
            cv2.destroyAllWindows()
    return frames


def _crop_with_margin(frame, location, margin=0.6):
    """Crop around a face box, padded by `margin` x its size on every side."""
    top, right, bottom, left = location
    pad_y = int((bottom - top) * margin)
    pad_x = int((right - left) * margin)
    height, width = frame.shape[:2]
    return frame[max(0, top - pad_y) : min(height, bottom + pad_y), max(0, left - pad_x) : min(width, right + pad_x)]


def capture_enrollment(
    recognizer,
    name,
    faces_dir,
    source=0,
    samples=5,
    interval=0.7,
    timeout=60.0,
    display=True,
    num_jitters=ENROLL_JITTERS,
):
    """Enroll `name` from the camera: save `samples` face photos and add their encodings.

    A sample is taken whenever exactly one clear face is visible, at most once
    per `interval` seconds, so turning your head slightly between shots gives
    varied angles. Photos go to faces_dir/<name>/ (cropped around the face) so
    a later full rebuild from the folder reproduces the same enrollment.
    Returns the list of saved photo paths.
    """
    name = validate_person_name(name)
    person_dir = Path(faces_dir) / name
    # If the database matches the folder now, it will still match after we add
    # both the photos and their encodings, so it won't need a rebuild.
    start_fingerprint = photos_fingerprint(faces_dir)
    database_was_fresh = recognizer.database.source == start_fingerprint
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    capture = open_capture(source)
    saved, encodings = [], []
    warned_other = False
    last_shot = 0.0
    deadline = time.monotonic() + timeout
    try:
        while len(saved) < samples and time.monotonic() < deadline:
            ok, frame = capture.read()
            if not ok:
                break
            rgb, locations = recognizer.locate_in_bgr_frame(frame)
            index = pick_enrollment_face(locations)
            now = time.monotonic()
            if index is not None and now - last_shot >= interval:
                location = locations[index]
                [encoding] = recognizer.encode(rgb, [location], num_jitters=num_jitters)
                match = recognizer.database.match(encoding, recognizer.config.tolerance)
                if match.is_known and match.name != name and not warned_other:
                    logger.warning("this face already matches %r (distance %.2f); enrolling as %r anyway", match.name, match.distance, name)
                    warned_other = True
                path = person_dir / f"capture_{stamp}_{len(saved) + 1}.jpg"
                save_bgr(path, _crop_with_margin(frame, location))
                saved.append(path)
                encodings.append(encoding)
                last_shot = now
                logger.info("captured %d/%d -> %s", len(saved), samples, path)

            if display:
                status = f"{name}: {len(saved)}/{samples}"
                if not locations:
                    status += "  (no face)"
                elif index is None:
                    status += "  (one person only)"
                for i, (top, right, bottom, left) in enumerate(locations):
                    color = KNOWN_COLOR if i == index else UNKNOWN_COLOR
                    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.putText(frame, status, (10, 25), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 2)
                if not _show(frame):
                    break
    finally:
        capture.release()
        if display:
            cv2.destroyAllWindows()

    if encodings:
        recognizer.database.add(name, np.array(encodings))
        # ...unless someone else changed the folder meanwhile; then leave it stale.
        if database_was_fresh and photos_fingerprint(faces_dir, exclude=saved) == start_fingerprint:
            recognizer.database.source = photos_fingerprint(faces_dir)
    if len(saved) < samples:
        logger.warning("captured only %d of %d samples for %s", len(saved), samples, name)
    return saved

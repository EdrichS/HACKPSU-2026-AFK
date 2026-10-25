"""The camera side: a window with every face boxed and, when the database knows it, named."""

import logging
import threading
import time
from dataclasses import dataclass

import cv2

from contract.embedders import Box, FaceDetection
from contract.live import PresentPerson
from db.match import decide, nearest_people
from enroll import ui
from facerec.video import open_capture
from live.voices import to_present

log = logging.getLogger("live.faces")

WINDOW = "Nametags live"
MAX_WIDTH = 1280
CAPTURE_SIZE = (1280, 720)  # asked of the camera; fewer pixels than 1080p for everything after
COLORS = {"named": ui.GREEN, "not_sure": ui.AMBER, "no_match": ui.RED}


class FaceIdentifier:
    """One detected face -> the person it belongs to, by the rules in db.match (nothing cached)."""

    def __init__(self, embedder, pool, margin: float = 0.05):
        self.embedder = embedder
        self.pool = pool
        self.margin = margin

    def identify(self, face: FaceDetection) -> tuple[PresentPerson | None, str, float | None]:
        with self.pool.connection() as conn:
            candidates = nearest_people(conn, "face", self.embedder.spec.metric, face.embedding)
        verdict = decide(candidates, self.embedder.spec.cutoff, self.margin)
        nearest = candidates[0].distance if candidates else None
        if isinstance(verdict, str):
            return None, verdict, nearest
        return to_present(verdict), "named", verdict.distance


@dataclass
class LabelledFace:
    box: Box
    person: PresentPerson | None
    verdict: str
    distance: float | None


class FaceWatcher:
    """The camera loop. Frames are read and drawn in the main thread (OpenCV windows need it);
    detection runs on a worker thread, at most `rate` times a second on the latest frame, so the
    window stays smooth and the microphone thread keeps getting its share of the interpreter."""

    def __init__(self, embedder, identifier: FaceIdentifier, presence, source=0, rate: float = 3.0, display: bool = True):
        self.embedder = embedder
        self.identifier = identifier
        self.presence = presence
        self.source = source
        self.rate = rate
        self.display = display
        self.faces: list[LabelledFace] = []
        self._latest = None
        self._lock = threading.Lock()

    def run(self, stop: threading.Event, overlay, on_key, on_arrival, on_unknown, on_tick=None) -> int:
        """Until `stop` is set, q, or the window closes. overlay() gives the lines to draw;
        on_key(char) gets any other key; on_arrival(text, person) and on_unknown(text) get
        sentences to speak; on_tick() runs once per frame. Returns the number of frames read."""
        capture = open_capture(self.source)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_SIZE[0])
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_SIZE[1])
        if self.display:
            cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        worker = threading.Thread(target=self._worker, args=(stop, on_arrival, on_unknown), daemon=True, name="face-worker")
        worker.start()
        frames = 0
        try:
            while not stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    break
                with self._lock:
                    self._latest = frame
                frames += 1
                if on_tick is not None:
                    on_tick()
                if self.display:
                    cv2.imshow(WINDOW, render(frame, self.faces, overlay()))
                    key = cv2.waitKey(1) & 0xFF
                    if ui.closed(WINDOW) or key in (ord("q"), 27):
                        break
                    if key != 255:
                        on_key(chr(key))
                else:
                    time.sleep(0.01)
        finally:
            stop.set()
            capture.release()
            if self.display:
                ui.close(WINDOW)
        return frames

    def _worker(self, stop: threading.Event, on_arrival, on_unknown) -> None:
        interval = 1.0 / max(self.rate, 0.1)
        while not stop.is_set():
            started = time.monotonic()
            with self._lock:
                frame, self._latest = self._latest, None
            if frame is None:
                time.sleep(0.01)
                continue
            try:
                self.faces = self._look(frame, on_arrival, on_unknown)
            except Exception as e:  # noqa: BLE001  (one bad frame must not end the loop)
                log.error("face detection failed: %s: %s", type(e).__name__, e)
            rest = interval - (time.monotonic() - started)
            if rest > 0:
                time.sleep(rest)

    def _look(self, frame, on_arrival, on_unknown) -> list[LabelledFace]:
        rgb, locations = self.embedder.recognizer.locate_in_bgr_frame(frame)
        labelled = []
        unknown_in_view = False
        for face in self.embedder.detect_faces_rgb(rgb, locations):
            person, verdict, distance = self.identifier.identify(face)
            labelled.append(LabelledFace(face.box, person, verdict, distance))
            if person is not None:
                text = self.presence.saw(person, "face")
                if text:
                    on_arrival(text, person)
            elif verdict == "no_match":
                unknown_in_view = True
        text = self.presence.unknown_face(unknown_in_view)
        if text:
            on_unknown(text)
        return labelled


def render(frame, faces: list[LabelledFace], overlay: list[str]):
    """The frame with boxes and names, and the status lines down the left."""
    shown, scale = ui.fit(frame, MAX_WIDTH)
    height, width = shown.shape[:2]
    for f in faces:
        x1, y1 = int(f.box.x * scale), int(f.box.y * scale)
        x2, y2 = int((f.box.x + f.box.width) * scale), int((f.box.y + f.box.height) * scale)
        color = COLORS.get(f.verdict, ui.RED)
        cv2.rectangle(shown, (x1, y1), (x2, y2), color, 2)
        if f.person is not None:
            label = f"{f.person.name}, {f.person.relationship}"
        elif f.verdict == "not_sure":
            label = "?"
        else:
            label = "unknown"
        ui.text(shown, label, (x1, max(22, y1 - 8)), 0.65, color)
    y = 30
    for line in overlay:
        if line:
            ui.text(shown, line, (12, y), 0.55)
        y += 26
    ui.text(shown, "q: quit    e: end the visit (summarize)    w: who is here?", (12, height - 12), 0.5)
    return shown

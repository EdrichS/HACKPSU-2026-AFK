"""The voice recording pop-up: a record button, the passage to read, and a speech meter."""

import time

import cv2
import numpy as np

from enroll import ui
from enroll.mic import MIN_TOTAL, PASSAGE, TIPS, SpeechRecorder

WINDOW = "Nametags enrollment: voice"
WIDTH, HEIGHT, MARGIN = 960, 680, 24
BUTTON_CENTER, BUTTON_RADIUS = (WIDTH // 2, HEIGHT - 95), 40


def record_in_window(name: str, seconds: float, device=None) -> np.ndarray | None:
    """Pop up the recording window and return the speech recorded, or None if it was cancelled.

    The microphone opens at once so the level meter shows it works. Clicking the red button (or
    pressing space) starts counting speech; the recording ends by itself once `seconds` of speech
    are in, or on another click once at least MIN_TOTAL seconds are. q or closing the window cancels.
    """
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    clicks = ui.Clicks(WINDOW)
    notice, notice_until = "", 0.0
    try:
        with SpeechRecorder(seconds, device) as recorder:
            while True:
                recorder.poll()
                if recorder.armed and recorder.done:
                    return _finish(name, recorder)
                cv2.imshow(WINDOW, _draw(name, recorder, notice if time.monotonic() < notice_until else ""))
                key = cv2.waitKey(30) & 0xFF
                if ui.closed(WINDOW) or key in (ord("q"), 27):
                    return None
                clicked = any(ui.inside(BUTTON_CENTER, BUTTON_RADIUS, p) for p in clicks.take())
                if key == ord(" ") or clicked:
                    if not recorder.armed:
                        recorder.start()
                    elif recorder.total >= MIN_TOTAL:
                        return _finish(name, recorder)
                    else:
                        notice = f"Keep talking: at least {MIN_TOTAL:.0f} seconds of speech are needed."
                        notice_until = time.monotonic() + 2.5
    finally:
        ui.close(WINDOW)


def _finish(name: str, recorder: SpeechRecorder) -> np.ndarray:
    speech = recorder.finish()
    canvas = _draw(name, recorder, "")
    ui.text(canvas, "Saved", (BUTTON_CENTER[0] - 40, BUTTON_CENTER[1] + 10), 0.9, ui.GREEN, 2, outline=False)
    cv2.imshow(WINDOW, canvas)
    cv2.waitKey(600)
    return speech


def _draw(name: str, recorder: SpeechRecorder, notice: str) -> np.ndarray:
    canvas = np.full((HEIGHT, WIDTH, 3), ui.BACKGROUND, np.uint8)
    width = WIDTH - 2 * MARGIN
    ui.text(canvas, f"Record {name}'s voice", (MARGIN, 50), 1.0, thickness=2, outline=False)
    y = ui.paragraph(canvas, TIPS, (MARGIN, 90), width, 0.5, ui.LIGHT_GREY)
    ui.text(canvas, "Read this out loud, then keep talking:", (MARGIN, y + 20), 0.6, ui.AMBER, outline=False)
    ui.paragraph(canvas, PASSAGE.format(name=name), (MARGIN, y + 56), width, 0.62)

    top = HEIGHT - 235
    collected = recorder.total + recorder.live
    ui.text(canvas, f"speech collected: {collected:4.1f} / {recorder.seconds:.0f} s", (MARGIN, top), 0.6, outline=False)
    ui.bar(canvas, (MARGIN, top + 12), (width, 22), recorder.progress, ui.GREEN)
    if not recorder.armed:
        state = "microphone check: the meter should move when you talk"
    else:
        state = "speaking" if recorder.speaking else "listening..."
    ui.text(canvas, state, (MARGIN, top + 66), 0.55, ui.LIGHT_GREY, outline=False)
    ui.bar(canvas, (MARGIN, top + 78), (320, 14), ui.level_fraction(recorder.level), ui.BLUE)

    if not recorder.armed:
        ui.round_button(canvas, BUTTON_CENTER, BUTTON_RADIUS, ui.RED, "click, or press space, to start recording")
    else:
        ui.round_button(canvas, BUTTON_CENTER, BUTTON_RADIUS, ui.RED, "recording...  click, or press space, to finish", square=True)
    ui.text(canvas, "q: cancel", (WIDTH - 120, HEIGHT - 16), 0.5, ui.LIGHT_GREY, outline=False)
    if notice:
        ui.text(canvas, notice, (MARGIN + 340, top + 91), 0.6, ui.AMBER, outline=False)
    return canvas

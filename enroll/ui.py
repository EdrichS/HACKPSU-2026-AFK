"""Drawing and input helpers for the enrollment pop-up windows (OpenCV HighGUI)."""

import math

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX
WHITE, BLACK, GREY, LIGHT_GREY = (255, 255, 255), (0, 0, 0), (90, 90, 90), (190, 190, 190)
GREEN, RED, AMBER, BLUE = (0, 200, 0), (40, 40, 230), (0, 180, 255), (230, 150, 40)
BACKGROUND = (34, 30, 28)


def text(image, s, xy, scale=0.7, color=WHITE, thickness=1, outline=True) -> None:
    """Draw one line of text; `outline` puts a dark plate behind it so it reads over a camera frame.

    (A thick black stroke under the text would seem simpler, but OpenCV spaces glyphs wider at
    higher thickness, so the two drift apart along the line.)
    """
    if outline:
        (w, h), baseline = cv2.getTextSize(s, FONT, scale, thickness)
        x, y = xy
        x1, y1 = max(0, x - 6), max(0, y - h - 6)
        x2, y2 = min(image.shape[1], x + w + 6), min(image.shape[0], y + baseline + 4)
        if x2 > x1 and y2 > y1:
            plate = image[y1:y2, x1:x2]
            cv2.addWeighted(plate, 0.4, np.zeros_like(plate), 0.6, 0, dst=plate)
    cv2.putText(image, s, xy, FONT, scale, color, thickness, cv2.LINE_AA)


def text_width(s, scale, thickness=1) -> int:
    return cv2.getTextSize(s, FONT, scale, thickness)[0][0]


def wrap(s, width, scale=0.6, thickness=1) -> list[str]:
    """Break `s` into lines no wider than `width` pixels at this font size."""
    lines, line = [], ""
    for word in s.split():
        candidate = f"{line} {word}".strip()
        if line and text_width(candidate, scale, thickness) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def paragraph(image, s, xy, width, scale=0.6, color=WHITE) -> int:
    """Draw wrapped text; return the y just below it."""
    x, y = xy
    step = int(36 * scale / 0.6)
    for line in wrap(s, width, scale):
        text(image, line, (x, y), scale, color, outline=False)
        y += step
    return y


def bar(image, xy, size, fraction, color=GREEN, background=GREY) -> None:
    x, y = xy
    w, h = size
    cv2.rectangle(image, (x, y), (x + w, y + h), background, cv2.FILLED)
    filled = int(round(max(0.0, min(1.0, fraction)) * w))
    if filled:
        cv2.rectangle(image, (x, y), (x + filled, y + h), color, cv2.FILLED)
    cv2.rectangle(image, (x, y), (x + w, y + h), WHITE, 1)


def round_button(image, center, radius, color, label=None, square=False) -> None:
    """A shutter or record button: a ring with a disc (or a stop square) inside, and a caption below."""
    cv2.circle(image, center, radius, WHITE, 3, cv2.LINE_AA)
    cx, cy = center
    if square:
        s = int(radius * 0.45)
        cv2.rectangle(image, (cx - s, cy - s), (cx + s, cy + s), color, cv2.FILLED)
    else:
        cv2.circle(image, center, radius - 8, color, cv2.FILLED, cv2.LINE_AA)
    if label:
        text(image, label, (cx - text_width(label, 0.55) // 2, cy + radius + 28), 0.55)


def inside(center, radius, point) -> bool:
    (cx, cy), (x, y) = center, point
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def level_fraction(rms_value: float) -> float:
    """0..1 from an RMS level, mapping -50 dB..0 dB."""
    db = 20 * math.log10(max(rms_value, 1e-6))
    return max(0.0, min(1.0, (db + 50) / 50))


def fit(image, max_width: int):
    """Shrink `image` to at most `max_width` wide; return (image, scale applied)."""
    height, width = image.shape[:2]
    if width <= max_width:
        return image, 1.0
    scale = max_width / width
    return cv2.resize(image, (max_width, int(round(height * scale))), interpolation=cv2.INTER_AREA), scale


class Clicks:
    """Collects left clicks on a window; call take() once per frame."""

    def __init__(self, window: str):
        self._points: list[tuple[int, int]] = []
        cv2.setMouseCallback(window, self._on_mouse)

    def _on_mouse(self, event, x, y, flags, param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            self._points.append((x, y))

    def take(self) -> list[tuple[int, int]]:
        points, self._points = self._points, []
        return points


def closed(window: str) -> bool:
    """True once the person closed the window with its X button."""
    try:
        return cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def close(window: str) -> None:
    try:
        cv2.destroyWindow(window)
    except cv2.error:
        pass
    cv2.waitKey(1)  # lets the window really close on macOS

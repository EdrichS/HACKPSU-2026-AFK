"""Image loading, color conversion and drawing helpers.

Conventions used throughout this package:
  * face_recognition/dlib want RGB uint8 arrays that are C-contiguous.
    A view like `frame[:, :, ::-1]` is NOT contiguous and makes dlib raise
    "compute_face_descriptor(): incompatible function arguments".
  * OpenCV (camera frames, cv2.imshow, cv2.imwrite) uses BGR.
  * Face locations are (top, right, bottom, left) tuples, as returned by
    face_recognition.face_locations.
"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".webp", ".avif", ".gif", ".tif", ".tiff"}
# Photo formats Pillow can't open; reported during enrollment instead of silently ignored.
UNSUPPORTED_PHOTO_EXTENSIONS = {".heic", ".heif"}

KNOWN_COLOR = (0, 200, 0)  # BGR
UNKNOWN_COLOR = (0, 0, 220)


def load_image(path, max_size=None):
    """Load an image file as a contiguous RGB uint8 array.

    Applies the EXIF orientation tag first. face_recognition.load_image_file
    skips this, so portrait phone photos come in sideways and no face is found.
    If `max_size` is given, the image is shrunk so its longer side is at most
    that many pixels (faster detection on big phone photos).
    """
    try:
        im = Image.open(path)
    except Image.DecompressionBombError as exc:  # not an OSError, so callers wouldn't catch it
        raise ValueError(f"image too large: {exc}") from exc
    with im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        if max_size and max(im.size) > max_size:
            im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return np.ascontiguousarray(np.asarray(im, dtype=np.uint8))


def to_rgb(image):
    """Coerce grayscale/RGBA/non-contiguous arrays into a contiguous RGB uint8 array."""
    image = np.asarray(image)
    if image.dtype != np.uint8:
        raise ValueError(f"expected a uint8 image, got dtype {image.dtype}")
    if image.ndim == 2:
        image = np.stack([image] * 3, axis=-1)
    elif image.ndim == 3 and image.shape[2] == 4:
        image = image[:, :, :3]
    elif image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected an HxW, HxWx3 or HxWx4 image, got shape {image.shape}")
    return np.ascontiguousarray(image)


def bgr_to_rgb(frame):
    """OpenCV BGR frame -> contiguous RGB array (cvtColor always returns a new contiguous array)."""
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def rgb_to_bgr(image):
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def scale_location(location, scale_y, scale_x, image_shape):
    """Scale a (top, right, bottom, left) box and clip it to `image_shape`."""
    top, right, bottom, left = location
    height, width = image_shape[:2]
    return (
        max(0, int(round(top * scale_y))),
        min(width, int(round(right * scale_x))),
        min(height, int(round(bottom * scale_y))),
        max(0, int(round(left * scale_x))),
    )


def box_area(location):
    top, right, bottom, left = location
    return max(0, bottom - top) * max(0, right - left)


def draw_faces(bgr_frame, faces, show_confidence=True):
    """Draw a box and name label for each RecognizedFace onto `bgr_frame` (in place)."""
    for face in faces:
        top, right, bottom, left = face.location
        color = KNOWN_COLOR if face.is_known else UNKNOWN_COLOR
        label = face.name
        if show_confidence and face.is_known:
            label = f"{face.name} {face.confidence:.0%}"

        cv2.rectangle(bgr_frame, (left, top), (right, bottom), color, 2)
        (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.6, 1)
        label_top = max(0, bottom - text_h - baseline - 8)
        cv2.rectangle(bgr_frame, (left, label_top), (max(right, left + text_w + 12), bottom), color, cv2.FILLED)
        cv2.putText(bgr_frame, label, (left + 6, bottom - baseline - 4), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)
    return bgr_frame


def save_bgr(path, bgr_image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), bgr_image):
        raise OSError(f"could not write image to {path}")

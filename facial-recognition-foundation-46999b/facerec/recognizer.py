"""Detect, encode and identify faces with the face_recognition 1.3 API."""

from dataclasses import dataclass, field

import cv2
import numpy as np

from ._deps import load_face_recognition
from .config import FaceConfig
from .database import UNKNOWN, FaceDatabase
from .imaging import bgr_to_rgb, box_area, scale_location, to_rgb


@dataclass
class RecognizedFace:
    location: tuple  # (top, right, bottom, left) in the input image's pixel coordinates
    name: str  # UNKNOWN if no enrolled face is within tolerance
    distance: float  # lower = more similar; compare against FaceConfig.tolerance
    confidence: float  # 0..1 display score, see database.distance_to_confidence
    # The raw 128-d vector. Adding it to recognizer.database only lasts until the
    # next rebuild from the photo folder; to enroll for good, save a photo to
    # faces_dir/<name>/ (as video.capture_enrollment does).
    encoding: np.ndarray = field(repr=False, compare=False)

    @property
    def is_known(self):
        return self.name != UNKNOWN


class FaceRecognizer:
    """Wraps face_recognition with a FaceDatabase and FaceConfig.

    Use identify() for RGB images (files, PIL, face_recognition.load_image_file)
    and identify_bgr_frame() for OpenCV camera frames.
    """

    def __init__(self, database=None, config=None):
        self.config = config or FaceConfig()
        self.database = database if database is not None else FaceDatabase()
        self._fr = load_face_recognition()

    def detect(self, rgb_image):
        """Face boxes as (top, right, bottom, left) tuples, at the image's own resolution."""
        return self._fr.face_locations(
            to_rgb(rgb_image),
            number_of_times_to_upsample=self.config.upsample,
            model=self.config.detection_model,
        )

    def encode(self, rgb_image, locations, num_jitters=None):
        """128-d encoding for each box in `locations` (same order)."""
        if not locations:
            return []
        return self._fr.face_encodings(
            to_rgb(rgb_image),
            known_face_locations=locations,
            num_jitters=num_jitters or self.config.num_jitters,
            model=self.config.encoding_model,
        )

    def locate(self, rgb_image, scale=None):
        """Detect faces on a copy of `rgb_image` shrunk by `scale`; boxes are in full-size pixels.

        Detection cost grows with pixel count, encoding cost doesn't, so it pays
        to detect small and then encode from the full-resolution image. With
        scale=None, still-image sizing applies (see FaceConfig.max_image_size).
        """
        rgb = to_rgb(rgb_image)
        height, width = rgb.shape[:2]
        if height == 0 or width == 0:
            return []
        if scale is None:
            max_size = self.config.effective_max_image_size
            scale = min(1.0, max_size / max(height, width)) if max_size else 1.0
        if scale >= 1.0:
            return self.detect(rgb)

        # Explicit size: fx/fy would round a thin image's short side down to 0.
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        small = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        scale_y = rgb.shape[0] / small.shape[0]
        scale_x = rgb.shape[1] / small.shape[1]
        return [scale_location(loc, scale_y, scale_x, rgb.shape) for loc in self.detect(small)]

    def identify(self, image):
        """Find and name every face in an RGB image."""
        rgb = to_rgb(image)
        return self._identify_locations(rgb, self.locate(rgb))

    def identify_bgr_frame(self, bgr_frame):
        """Find and name every face in an OpenCV BGR frame. Locations are in full-frame pixels."""
        rgb, locations = self.locate_in_bgr_frame(bgr_frame)
        return self._identify_locations(rgb, locations)

    def locate_in_bgr_frame(self, bgr_frame):
        """Convert a BGR frame to RGB and detect faces at config.frame_scale. Returns (rgb, locations)."""
        rgb = bgr_to_rgb(bgr_frame)
        return rgb, self.locate(rgb, scale=self.config.frame_scale)

    def _identify_locations(self, rgb, locations):
        locations = [loc for loc in locations if box_area(loc) > 0]
        faces = []
        for location, encoding in zip(locations, self.encode(rgb, locations)):
            match = self.database.match(encoding, self.config.tolerance)
            faces.append(RecognizedFace(location, match.name, match.distance, match.confidence, encoding))
        return faces

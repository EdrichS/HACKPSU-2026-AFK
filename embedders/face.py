"""The face embedder for the contract, built on facerec (face_recognition 1.3 + dlib).

Implements contract.embedders.FaceEmbedder: one 128-number encoding per face found in a JPEG or
PNG, with its box in integer pixels of that image. The 128 numbers are what face_samples.embedding
vector(128) in db/schema.sql holds. The backend swaps this in for contract.fakes.FakeFaceEmbedder.
"""

import io
from dataclasses import replace

import numpy as np
from PIL import Image, ImageOps

from contract.embedders import Box, EmbedderSpec, FaceDetection
from facerec import FaceConfig, FaceRecognizer

DIMENSIONS = 128  # dlib's ResNet face encoder


def decode_image(data: bytes) -> np.ndarray:
    """JPEG or PNG bytes -> contiguous RGB uint8 array, with the EXIF orientation applied."""
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        return np.ascontiguousarray(np.asarray(im, dtype=np.uint8))


def location_to_box(location, width: int, height: int) -> Box | None:
    """facerec's (top, right, bottom, left) -> Box clipped to the image, or None if nothing is left."""
    top, right, bottom, left = location
    left, top = max(0, int(left)), max(0, int(top))
    right, bottom = min(width, int(right)), min(height, int(bottom))
    if right <= left or bottom <= top:
        return None
    return Box(x=left, y=top, width=right - left, height=bottom - top)


class FaceRecEmbedder:
    """`num_jitters` re-samples each face when encoding: 1 is fast (live video), 5 is steadier
    (enrollment). The model name stays the same either way, since both land in the same space."""

    def __init__(self, config: FaceConfig | None = None, num_jitters: int | None = None):
        config = config or FaceConfig()
        if num_jitters is not None:
            config = replace(config, num_jitters=num_jitters)
        self.recognizer = FaceRecognizer(config=config)
        self.spec = EmbedderSpec(
            dimensions=DIMENSIONS,
            metric="l2",
            cutoff=config.tolerance,  # face_recognition's distance threshold, 0.6 by default
            model=f"face_recognition-1.3-{config.encoding_model}",
        )

    def detect_faces(self, image: bytes) -> list[FaceDetection]:
        """Every face in a JPEG or PNG, with its box and encoding."""
        return self.detect_faces_rgb(decode_image(image))

    def detect_faces_rgb(self, rgb: np.ndarray, locations=None) -> list[FaceDetection]:
        """The same for an image already decoded to RGB; pass `locations` to skip detection."""
        height, width = rgb.shape[:2]
        if locations is None:
            locations = self.recognizer.locate(rgb)
        kept = [(loc, box) for loc in locations if (box := location_to_box(loc, width, height)) is not None]
        encodings = self.recognizer.encode(rgb, [loc for loc, _ in kept])
        return [
            FaceDetection(box=box, embedding=[float(x) for x in encoding])
            for (_, box), encoding in zip(kept, encodings)
        ]

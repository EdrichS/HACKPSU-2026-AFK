"""Tunable settings for detection, encoding and matching."""

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FACES_DIR = PROJECT_ROOT / "data" / "known_faces"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "face_db.npz"

DETECTION_MODELS = ("hog", "cnn")
ENCODING_MODELS = ("small", "large")
CNN_MAX_IMAGE_SIZE = 1600


@dataclass
class FaceConfig:
    # Max face distance that still counts as a match. face_recognition's default
    # is 0.6; lower is stricter (fewer false matches, more "Unknown").
    tolerance: float = 0.6

    # "hog" runs fine on a laptop CPU. "cnn" is more accurate (side profiles,
    # small faces) but is only real-time with a CUDA-enabled dlib build; on a
    # CPU it takes seconds and several GB of RAM per photo.
    detection_model: str = "hog"

    # How many times to upsample before detecting. Higher finds smaller faces
    # but costs roughly 4x per step.
    upsample: int = 1

    # Times to re-sample each face when encoding. 1 is fast; 5-10 gives
    # slightly more stable encodings, so it's worth it at enrollment time.
    num_jitters: int = 1

    # Landmark model used to align faces before encoding: "small" (5 points,
    # faster, library default) or "large" (68 points).
    encoding_model: str = "small"

    # Live video: detect on a frame shrunk by this factor, and only run
    # recognition on every Nth frame. HOG needs a face ~40px wide in the shrunk
    # frame, so on a 640x480 webcam 0.5 finds faces down to ~80px (~1.2m away);
    # 0.25 is faster but only finds faces within ~0.6m.
    frame_scale: float = 0.5
    process_every_n_frames: int = 2

    # Still images: detect on a copy whose longer side is at most this many
    # pixels; encodings still come from the full-resolution image. 0 = detect
    # at full resolution. None = automatic: full resolution for "hog" (finds
    # small faces in crowd shots; ~3-5s for a 12MP photo) and 1600 for "cnn"
    # (which needs tens of GB for a 12MP photo on a CPU). Faces narrower than
    # ~40px in the detection copy are missed.
    max_image_size: int | None = None

    def __post_init__(self):
        if self.detection_model not in DETECTION_MODELS:
            raise ValueError(f"detection_model must be one of {DETECTION_MODELS}, got {self.detection_model!r}")
        if self.encoding_model not in ENCODING_MODELS:
            raise ValueError(f"encoding_model must be one of {ENCODING_MODELS}, got {self.encoding_model!r}")
        if not 0.0 < self.tolerance <= 1.0:
            raise ValueError(f"tolerance must be in (0, 1], got {self.tolerance}")
        if not 0.0 < self.frame_scale <= 1.0:
            raise ValueError(f"frame_scale must be in (0, 1], got {self.frame_scale}")
        if self.upsample < 0:
            raise ValueError(f"upsample must be >= 0, got {self.upsample}")
        if self.num_jitters < 1:
            raise ValueError(f"num_jitters must be >= 1, got {self.num_jitters}")
        if self.process_every_n_frames < 1:
            raise ValueError(f"process_every_n_frames must be >= 1, got {self.process_every_n_frames}")
        if self.max_image_size not in (None, 0) and self.max_image_size < 64:
            raise ValueError(f"max_image_size must be None (auto), 0 (no limit) or >= 64, got {self.max_image_size}")

    @property
    def effective_max_image_size(self):
        """max_image_size with None resolved for the chosen detector (0 = no limit)."""
        if self.max_image_size is None:
            return CNN_MAX_IMAGE_SIZE if self.detection_model == "cnn" else 0
        return self.max_image_size

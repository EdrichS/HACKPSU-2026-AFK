"""Paths and defaults shared across the package."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"

SAMPLE_RATE = 16000  # every model here expects 16 kHz mono

# Speaker-embedding model (ONNX). Override with VOICEREC_MODEL=/path/to/model.onnx
DEFAULT_EMBED_MODEL = os.environ.get(
    "VOICEREC_MODEL", str(MODELS_DIR / "nemo_en_titanet_small.onnx")
)
VAD_MODEL = os.environ.get("VOICEREC_VAD_MODEL", str(MODELS_DIR / "silero_vad.onnx"))

# Where enrolled speakers are kept. Override with VOICEREC_DB=/path/to/speakers.json
DB_PATH = Path(os.environ.get("VOICEREC_DB", str(DATA_DIR / "speakers.json")))

# Cosine similarity needed to accept a match. Synthetic voices score 0.85+ against
# themselves, real people on a laptop mic in a busy room more like 0.45-0.75, so the
# bar sits at 0.45 (a clear winner a little under it is still accepted, see
# Recognizer). Raise it if strangers get matched, lower it if enrolled people show
# up as Unknown.
DEFAULT_THRESHOLD = float(os.environ.get("VOICEREC_THRESHOLD", "0.45"))

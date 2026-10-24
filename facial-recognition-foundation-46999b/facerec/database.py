"""Known-face store: names + 128-d encodings, matched by nearest neighbour.

Saved as a .npz file (numpy arrays only, loaded with allow_pickle=False) so a
database file can't execute code when loaded, unlike pickle.
"""

import math
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ENCODING_SIZE = 128
UNKNOWN = "Unknown"


@dataclass(frozen=True)
class Match:
    name: str  # UNKNOWN when no known face is within tolerance
    distance: float  # distance to the closest known encoding (inf if the database is empty)
    confidence: float  # 0..1, see distance_to_confidence()

    @property
    def is_known(self):
        return self.name != UNKNOWN


def distance_to_confidence(distance, tolerance=0.6):
    """Map a face distance to a 0..1 score where `tolerance` maps to 0.5.

    This is a display heuristic (from the face_recognition wiki), not a
    calibrated probability: it bends the curve so clear matches read as ~90%+
    instead of the raw linear 60-70%.
    """
    if distance > tolerance:
        span = 1.0 - tolerance
        if span <= 0:
            return 0.0
        return max(0.0, (1.0 - distance) / (span * 2.0))
    linear = 1.0 - distance / (tolerance * 2.0)
    return linear + (1.0 - linear) * math.pow((linear - 0.5) * 2.0, 0.2)


def _as_encoding_matrix(encodings):
    matrix = np.asarray(encodings, dtype=np.float64)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2 or matrix.shape[1] != ENCODING_SIZE:
        raise ValueError(f"expected encodings of shape (n, {ENCODING_SIZE}), got {matrix.shape}")
    return matrix


def _validate_name(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    name = name.strip()
    if name == UNKNOWN:
        raise ValueError(f"{UNKNOWN!r} is reserved for unrecognized faces")
    try:
        name.encode("utf-8")  # lone surrogates crash cv2.putText and printing
    except UnicodeEncodeError:
        raise ValueError(f"name {name!r} is not valid UTF-8") from None
    return name


class FaceDatabase:
    """Labelled face encodings. A person can have several encodings (one per photo).

    `source` records which photo set the encodings came from (see
    enroll.photos_fingerprint) so a stale cache can be detected.
    """

    def __init__(self, names=(), encodings=None, source=""):
        self.source = source
        self._names = [_validate_name(n) for n in names]
        if encodings is None:
            self._encodings = np.empty((0, ENCODING_SIZE), dtype=np.float64)
        else:
            self._encodings = _as_encoding_matrix(encodings)
        if len(self._names) != len(self._encodings):
            raise ValueError(f"{len(self._names)} names but {len(self._encodings)} encodings")

    def __len__(self):
        return len(self._names)

    @property
    def names(self):
        """Name for each stored encoding (same order as `encodings`)."""
        return list(self._names)

    @property
    def encodings(self):
        return self._encodings.copy()

    @property
    def people(self):
        return sorted(set(self._names))

    def counts(self):
        """Number of stored encodings per person."""
        result = {}
        for name in self._names:
            result[name] = result.get(name, 0) + 1
        return dict(sorted(result.items()))

    def add(self, name, encodings):
        """Add one encoding (shape (128,)) or several (shape (n, 128)) for `name`."""
        name = _validate_name(name)
        matrix = _as_encoding_matrix(encodings)
        self._encodings = np.vstack([self._encodings, matrix])
        self._names.extend([name] * len(matrix))

    def remove(self, name):
        """Delete every encoding for `name`. Returns how many were removed."""
        name = name.strip()
        keep =[i for i, n in enumerate(self._names) if n != name]
        removed = len(self._names) - len(keep)
        self._names = [self._names[i] for i in keep]
        self._encodings = self._encodings[keep]
        return removed

    def distances(self, encoding):
        """Euclidean distance from `encoding` to every stored encoding."""
        if len(self) == 0:
            return np.empty(0)
        return np.linalg.norm(self._encodings - np.asarray(encoding, dtype=np.float64), axis=1)

    def match(self, encoding, tolerance=0.6):
        """Closest known person, or UNKNOWN if nobody is within `tolerance`."""
        distances = self.distances(encoding)
        if distances.size == 0:
            return Match(UNKNOWN, math.inf, 0.0)
        best = int(np.argmin(distances))
        distance = float(distances[best])
        name = self._names[best] if distance <= tolerance else UNKNOWN
        return Match(name, distance, distance_to_confidence(distance, tolerance))

    def save(self, path):
        """Write to `path` atomically (a crash mid-save can't corrupt the old file)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        try:
            # Pass a file object: np.savez appends ".npz" to bare paths that lack it.
            with open(tmp, "wb") as f:
                np.savez(f, names=np.array(self._names, dtype=str), encodings=self._encodings, source=np.array(self.source))
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path):
        """Load a saved database. Raises OSError if unreadable, ValueError if not a valid database."""
        try:
            data = np.load(path, allow_pickle=False)
            if not isinstance(data, np.lib.npyio.NpzFile):  # a plain .npy array
                raise ValueError("not an .npz archive")
            with data:
                names = [str(n) for n in data["names"]]
                encodings = data["encodings"]
                source = str(data["source"]) if "source" in data.files else ""
        except (ValueError, KeyError, EOFError, zipfile.BadZipFile) as exc:
            raise ValueError(f"{path} is not a valid face database ({exc}); delete it or run `python -m facerec enroll`") from exc
        if not names:
            return cls(source=source)
        return cls(names, encodings, source)

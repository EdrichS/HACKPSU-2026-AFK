"""Build the face database from a folder of labelled photos.

The photo folder is the source of truth; the .npz database is a cache of
encodings computed from it. Layout:

    data/known_faces/
        alice/          <- one folder per person (preferred: several photos each)
            1.jpg
            2.png
        bob.jpg         <- or a single photo; the file name is the person's name
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .config import DEFAULT_DB_PATH, DEFAULT_FACES_DIR
from .database import UNKNOWN, FaceDatabase
from .imaging import IMAGE_EXTENSIONS, UNSUPPORTED_PHOTO_EXTENSIONS, box_area, load_image

logger = logging.getLogger(__name__)

# Enrollment photos are shrunk to this size first. Encodings are computed from a
# 150x150 face crop, so this loses nothing and makes 12MP phone photos fast.
ENROLL_MAX_SIZE = 1600

# Extra re-sampling per enrollment photo; slower but slightly more stable encodings.
ENROLL_JITTERS = 5

# With several faces in a photo, enroll the biggest one only if it's at least
# this many times larger than the next (e.g. a selfie with people far behind).
# Otherwise the photo is ambiguous and skipped rather than risk enrolling the
# wrong person.
DOMINANT_FACE_RATIO = 1.5

# Characters that can't appear in a folder name on Windows, macOS or Linux.
_INVALID_NAME_CHARS = set('<>:"/\\|?*')


@dataclass
class EnrollmentReport:
    added: dict = field(default_factory=dict)  # name -> number of photos enrolled
    skipped: list = field(default_factory=list)  # (path, reason)

    def summary(self):
        people = len(self.added)
        photos = sum(self.added.values())
        return f"enrolled {photos} photo(s) of {people} person(s), skipped {len(self.skipped)}"


def validate_person_name(name):
    """Names become folder names, so reject anything that could escape the faces dir."""
    name = name.strip()
    if (
        not name
        or name.startswith(".")
        or any(c in _INVALID_NAME_CHARS or ord(c) < 32 for c in name)
    ):
        raise ValueError(f"invalid person name {name!r}")
    if name == UNKNOWN:
        raise ValueError(f"{UNKNOWN!r} is reserved for unrecognized faces")
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:  # folder name in a non-UTF-8 encoding, e.g. from an old zip
        raise ValueError(f"invalid person name {name!r}: not valid UTF-8, rename the folder") from None
    return name


def _iter_files(faces_dir, extensions):
    faces_dir = Path(faces_dir)
    if not faces_dir.is_dir():
        return
    for entry in sorted(faces_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            for path in sorted(entry.rglob("*")):
                if path.suffix.lower() in extensions and not path.name.startswith(".") and path.is_file():
                    yield entry.name, path
        elif entry.suffix.lower() in extensions and entry.is_file():
            yield entry.stem, entry


def iter_labeled_images(faces_dir):
    """Yield (name, path) for every photo under `faces_dir`, in a stable order."""
    return _iter_files(faces_dir, IMAGE_EXTENSIONS)


def photos_fingerprint(faces_dir, exclude=()):
    """Hash of the photo set (folder, file paths, sizes, mtimes) under `faces_dir`.

    Stored in the database to tell when it's out of date. Unlike comparing
    mtimes, this also notices photos copied with their old timestamps (cp -p,
    rsync -a, unzip), a different --faces-dir, and photos added mid-rebuild.
    Unsupported photos (HEIC) count too, so adding one triggers a rebuild that
    warns about it. Paths in `exclude` are left out.
    """
    faces_dir = Path(faces_dir)
    excluded = {Path(p).resolve() for p in exclude}
    digest = hashlib.sha256(os.fsencode(faces_dir.resolve()))
    for _, path in _iter_files(faces_dir, IMAGE_EXTENSIONS | UNSUPPORTED_PHOTO_EXTENSIONS):
        if excluded and path.resolve() in excluded:
            continue
        try:
            stat = path.stat()
        except OSError:  # e.g. deleted since listing
            continue
        digest.update(b"\0" + os.fsencode(path.relative_to(faces_dir)))
        digest.update(f"\0{stat.st_size}\0{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def pick_enrollment_face(locations, dominance=DOMINANT_FACE_RATIO):
    """Index of the face to enroll from `locations`, or None if there is no clear choice."""
    if not locations:
        return None
    if len(locations) == 1:
        return 0
    by_size = sorted(range(len(locations)), key=lambda i: box_area(locations[i]), reverse=True)
    largest, runner_up = by_size[0], by_size[1]
    if box_area(locations[largest]) >= dominance * box_area(locations[runner_up]):
        return largest
    return None


def encode_enrollment_face(recognizer, rgb, locations=None, num_jitters=ENROLL_JITTERS):
    """Return (encoding, location, None) for the person in `rgb`, or (None, None, reason)."""
    if locations is None:
        locations = recognizer.detect(rgb)
    if not locations:
        return None, None, "no face found"
    index = pick_enrollment_face(locations)
    if index is None:
        return None, None, f"{len(locations)} faces of similar size; use a photo of just this person"
    location = locations[index]
    [encoding] = recognizer.encode(rgb, [location], num_jitters=num_jitters)
    return encoding, location, None


def build_database(recognizer, faces_dir, num_jitters=ENROLL_JITTERS, max_size=ENROLL_MAX_SIZE):
    """Encode every photo under `faces_dir`. Returns (FaceDatabase, EnrollmentReport)."""
    # Fingerprint first: photos added while this runs make the result stale, not lost.
    database = FaceDatabase(source=photos_fingerprint(faces_dir))
    report = EnrollmentReport()
    for _, path in _iter_files(faces_dir, UNSUPPORTED_PHOTO_EXTENSIONS):
        reason = f"unsupported format {path.suffix}; convert it to JPG or PNG"
        report.skipped.append((path, reason))
        logger.warning("skip %s: %s", path, reason)
    for name, path in iter_labeled_images(faces_dir):
        try:
            name = validate_person_name(name)
            rgb = load_image(path, max_size=max_size)
        except (OSError, ValueError) as exc:  # PIL raises OSError subclasses for unreadable images
            report.skipped.append((path, str(exc)))
            logger.warning("skip %s: %s", path, exc)
            continue
        encoding, _, reason = encode_enrollment_face(recognizer, rgb, num_jitters=num_jitters)
        if encoding is None:
            report.skipped.append((path, reason))
            logger.warning("skip %s: %s", path, reason)
            continue
        database.add(name, encoding)
        report.added[name] = report.added.get(name, 0) + 1
        logger.info("enrolled %s from %s", name, path)
    return database, report


def database_is_stale(faces_dir, db_path):
    """True if the database is missing, unreadable, or was built from a different set of photos.

    A missing faces folder never counts as stale, so a mistyped --faces-dir
    can't replace a good database with an empty one.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return True
    if not Path(faces_dir).is_dir():
        return False
    try:
        stored = FaceDatabase.load(db_path).source
    except (OSError, ValueError) as exc:
        logger.warning("rebuilding unreadable database: %s", exc)
        return True
    return stored != photos_fingerprint(faces_dir)


def load_or_build_database(recognizer, faces_dir=DEFAULT_FACES_DIR, db_path=DEFAULT_DB_PATH, num_jitters=ENROLL_JITTERS):
    """Load the cached database into `recognizer`, rebuilding it first if photos changed."""
    if not Path(faces_dir).is_dir():
        logger.warning("faces folder %s not found; add photos as %s/<name>/photo.jpg", faces_dir, faces_dir)
    if database_is_stale(faces_dir, db_path):
        logger.info("building face database from %s ...", faces_dir)
        database, report = build_database(recognizer, faces_dir, num_jitters=num_jitters)
        database.save(db_path)
        logger.info("%s -> %s", report.summary(), db_path)
    else:
        database = FaceDatabase.load(db_path)
    recognizer.database = database
    return database

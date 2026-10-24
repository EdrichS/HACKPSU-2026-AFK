import os
import shutil

import pytest

from facerec.database import UNKNOWN, FaceDatabase
from facerec.enroll import (
    build_database,
    database_is_stale,
    iter_labeled_images,
    photos_fingerprint,
    pick_enrollment_face,
    validate_person_name,
)


def test_iter_labeled_images_folders_and_flat_files(tmp_path):
    (tmp_path / "alice").mkdir()
    (tmp_path / "alice" / "1.jpg").touch()
    (tmp_path / "alice" / "2.PNG").touch()
    (tmp_path / "alice" / "notes.txt").touch()
    (tmp_path / "alice" / ".hidden.jpg").touch()
    (tmp_path / "bob.jpeg").touch()
    (tmp_path / ".DS_Store").touch()
    (tmp_path / "README.md").touch()

    found = [(name, path.name) for name, path in iter_labeled_images(tmp_path)]
    assert found == [("alice", "1.jpg"), ("alice", "2.PNG"), ("bob", "bob.jpeg")]


def test_iter_labeled_images_missing_dir(tmp_path):
    assert list(iter_labeled_images(tmp_path / "nope")) == []


def test_pick_enrollment_face():
    big = (0, 200, 200, 0)  # 200x200
    small = (0, 50, 50, 0)  # 50x50
    similar = (0, 190, 190, 0)
    assert pick_enrollment_face([]) is None
    assert pick_enrollment_face([small]) == 0
    assert pick_enrollment_face([small, big]) == 1
    assert pick_enrollment_face([big, similar]) is None  # ambiguous: skip rather than guess


@pytest.mark.parametrize("bad", ["", "  ", ".", "..", ".hidden", "a/b", "a\\b", "D:..", 'say "hi"', "tab\there", UNKNOWN])
def test_validate_person_name_rejects(bad):
    with pytest.raises(ValueError):
        validate_person_name(bad)


def test_validate_person_name_accepts_and_strips():
    assert validate_person_name("  Ada Lovelace ") == "Ada Lovelace"


def _make_faces(tmp_path):
    faces = tmp_path / "faces"
    (faces / "alice").mkdir(parents=True)
    (faces / "alice" / "1.jpg").write_bytes(b"a")
    return faces


def _save_built_from(faces, db_path):
    FaceDatabase(source=photos_fingerprint(faces)).save(db_path)


def test_database_is_stale_tracks_photo_changes(tmp_path):
    faces = _make_faces(tmp_path)
    db_path = tmp_path / "db.npz"
    assert database_is_stale(faces, db_path)  # no database yet

    _save_built_from(faces, db_path)
    assert not database_is_stale(faces, db_path)

    (faces / "alice" / "1.jpg").write_bytes(b"edited")
    assert database_is_stale(faces, db_path)
    _save_built_from(faces, db_path)

    shutil.rmtree(faces / "alice")
    assert database_is_stale(faces, db_path)


def test_database_is_stale_with_old_mtime_copy(tmp_path):
    # cp -p / rsync -a / unzip keep the photo's old timestamp; it must still count.
    faces = _make_faces(tmp_path)
    db_path = tmp_path / "db.npz"
    _save_built_from(faces, db_path)
    new_photo = faces / "bob.jpg"
    new_photo.write_bytes(b"b")
    os.utime(new_photo, (0, 0))
    assert database_is_stale(faces, db_path)


def test_database_is_stale_with_other_faces_dir(tmp_path):
    faces = _make_faces(tmp_path)
    other = tmp_path / "other"
    shutil.copytree(faces, other)
    db_path = tmp_path / "db.npz"
    _save_built_from(faces, db_path)
    assert database_is_stale(other, db_path)


def test_database_is_stale_edge_cases(tmp_path):
    faces = _make_faces(tmp_path)
    db_path = tmp_path / "db.npz"
    _save_built_from(faces, db_path)
    # A mistyped --faces-dir keeps the existing database instead of emptying it.
    assert not database_is_stale(tmp_path / "typo", db_path)
    # Dangling symlinks are ignored rather than crashing.
    (faces / "alice" / "gone.jpg").symlink_to(tmp_path / "missing.jpg")
    assert not database_is_stale(faces, db_path)
    # A corrupt database gets rebuilt.
    db_path.write_bytes(b"garbage")
    assert database_is_stale(faces, db_path)


def test_build_database_reports_unsupported_photos(tmp_path):
    faces = tmp_path / "faces"
    (faces / "alice").mkdir(parents=True)
    (faces / "alice" / "IMG_0001.HEIC").write_bytes(b"x")
    (faces / "alice" / "notes.txt").write_bytes(b"x")
    database, report = build_database(recognizer=None, faces_dir=faces)  # no images -> recognizer unused
    assert len(database) == 0
    assert [(p.name, "unsupported" in why) for p, why in report.skipped] == [("IMG_0001.HEIC", True)]


def test_adding_heic_makes_database_stale(tmp_path):
    # So the rebuild runs and warns about it, instead of silently ignoring the photo.
    faces = _make_faces(tmp_path)
    db_path = tmp_path / "db.npz"
    _save_built_from(faces, db_path)
    (faces / "carol").mkdir()
    (faces / "carol" / "IMG_0001.HEIC").write_bytes(b"x")
    assert database_is_stale(faces, db_path)


def test_validate_person_name_rejects_undecodable_folder_names():
    with pytest.raises(ValueError, match="UTF-8"):
        validate_person_name("Jos\udce9")  # how Python decodes a latin-1 "José" folder name


@pytest.mark.parametrize("good", ["O'Brien", "José", "Mary-Jane", "李雷", "Martin Luther King Jr."])
def test_validate_person_name_accepts_real_names(good):
    assert validate_person_name(good) == good

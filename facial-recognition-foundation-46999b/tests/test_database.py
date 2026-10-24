import math

import numpy as np
import pytest
from conftest import random_encoding

from facerec.database import UNKNOWN, FaceDatabase, distance_to_confidence


def test_empty_database_matches_unknown():
    match = FaceDatabase().match(random_encoding(0))
    assert match.name == UNKNOWN
    assert math.isinf(match.distance)
    assert match.confidence == 0.0
    assert not match.is_known


def test_match_picks_nearest_within_tolerance():
    alice, bob = random_encoding(1), random_encoding(2)
    db = FaceDatabase()
    db.add("alice", alice)
    db.add("bob", bob)

    probe = alice + 0.02  # small perturbation of alice
    match = db.match(probe, tolerance=0.6)
    assert match.name == "alice"
    assert match.distance == pytest.approx(np.linalg.norm(probe - alice))
    assert match.confidence > 0.9


def test_match_outside_tolerance_is_unknown():
    db = FaceDatabase(["alice"], [random_encoding(1)])
    match = db.match(random_encoding(99), tolerance=0.6)
    assert match.name == UNKNOWN
    assert match.distance > 0.6
    assert match.confidence < 0.5


def test_tolerance_boundary_is_inclusive():
    base = np.zeros(128)
    probe = base.copy()
    probe[0] = 0.5
    db = FaceDatabase(["alice"], [base])
    assert db.match(probe, tolerance=0.5).name == "alice"
    assert db.match(probe, tolerance=0.49).name == UNKNOWN


def test_add_many_counts_and_remove():
    db = FaceDatabase()
    db.add("alice", np.stack([random_encoding(1), random_encoding(2)]))
    db.add("bob", random_encoding(3))
    assert len(db) == 3
    assert db.people == ["alice", "bob"]
    assert db.counts() == {"alice": 2, "bob": 1}

    assert db.remove("alice") == 2
    assert db.names == ["bob"]
    assert db.encodings.shape == (1, 128)
    assert db.remove("nobody") == 0


def test_save_load_roundtrip(tmp_path):
    db = FaceDatabase()
    db.add("Zoë O'Neil", random_encoding(1))  # non-ASCII and punctuation survive
    db.add("bob", random_encoding(2))
    path = tmp_path / "nested" / "faces.npz"
    db.save(path)

    loaded = FaceDatabase.load(path)
    assert loaded.names == db.names
    np.testing.assert_array_equal(loaded.encodings, db.encodings)
    assert not path.with_name(path.name + ".tmp").exists()


def test_save_keeps_exact_filename_without_npz_suffix(tmp_path):
    path = tmp_path / "faces.db"
    FaceDatabase(["a"], [random_encoding(1)]).save(path)
    assert path.exists()
    assert FaceDatabase.load(path).names == ["a"]


def test_empty_database_roundtrip(tmp_path):
    path = tmp_path / "empty.npz"
    FaceDatabase().save(path)
    assert len(FaceDatabase.load(path)) == 0


@pytest.mark.parametrize("bad", ["", "   ", UNKNOWN])
def test_rejects_bad_names(bad):
    with pytest.raises(ValueError):
        FaceDatabase().add(bad, random_encoding(0))


def test_rejects_wrong_encoding_shape():
    with pytest.raises(ValueError):
        FaceDatabase().add("alice", np.zeros(64))
    with pytest.raises(ValueError):
        FaceDatabase(["a", "b"], [random_encoding(1)])


def test_names_are_stripped():
    db = FaceDatabase()
    db.add("  alice ", random_encoding(1))
    assert db.names == ["alice"]
    assert db.remove(" alice") == 1


def test_confidence_curve():
    assert distance_to_confidence(0.0, 0.6) == pytest.approx(1.0)
    assert distance_to_confidence(0.6, 0.6) == pytest.approx(0.5)
    assert distance_to_confidence(5.0, 0.6) == 0.0
    distances = np.linspace(0, 1.2, 50)
    scores = [distance_to_confidence(d, 0.6) for d in distances]
    assert all(a >= b for a, b in zip(scores, scores[1:])), "confidence must not increase with distance"
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert distance_to_confidence(1.1, tolerance=1.0) == 0.0  # no division by zero


def test_source_roundtrip(tmp_path):
    path = tmp_path / "faces.npz"
    FaceDatabase(["a"], [random_encoding(1)], source="abc123").save(path)
    assert FaceDatabase.load(path).source == "abc123"


@pytest.mark.parametrize("content", [b"", b"garbage", b"PK\x03\x04truncated"])
def test_load_corrupt_file_raises_value_error(tmp_path, content):
    path = tmp_path / "bad.npz"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="not a valid face database"):
        FaceDatabase.load(path)


def test_failed_save_leaves_no_temp_file(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(np, "savez", boom)
    path = tmp_path / "faces.npz"
    with pytest.raises(KeyboardInterrupt):
        FaceDatabase(["a"], [random_encoding(1)]).save(path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", ["Unknown ", " Unknown", "Jos\udce9"])
def test_rejects_reserved_and_undecodable_names(bad):
    with pytest.raises(ValueError):
        FaceDatabase().add(bad, random_encoding(0))


def test_load_plain_npy_raises_value_error(tmp_path):
    path = tmp_path / "raw.npy"
    np.save(path, np.zeros(3))
    with pytest.raises(ValueError, match="not a valid face database"):
        FaceDatabase.load(path)

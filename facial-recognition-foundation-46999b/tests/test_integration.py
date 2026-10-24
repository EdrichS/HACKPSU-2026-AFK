"""End-to-end tests with the real dlib models on tests/fixtures/astronaut.jpg.

astronaut.jpg is NASA's public-domain portrait of Eileen Collins (shipped with
scikit-image as skimage.data.astronaut). The HOG detector also fires on her
round mission patch, which makes it a useful real-world false-positive case.
"""

import shutil

import cv2
import numpy as np
import pytest
from conftest import ASTRONAUT

from facerec import UNKNOWN, FaceDatabase
from facerec.cli import main
from facerec.enroll import build_database, encode_enrollment_face
from facerec.imaging import rgb_to_bgr
from facerec.video import run_live

pytestmark = pytest.mark.integration


def _face_center_in_upper_half(face):
    top, right, bottom, left = face.location
    return (top + bottom) / 2 < 250


def test_detects_face_and_mission_patch(recognizer_factory, astronaut_rgb):
    recognizer = recognizer_factory()
    locations = recognizer.detect(astronaut_rgb)
    assert len(locations) == 2
    encodings = recognizer.encode(astronaut_rgb, locations)
    assert [e.shape for e in encodings] == [(128,), (128,)]


def test_enrollment_skips_ambiguous_photo(recognizer_factory, astronaut_rgb):
    encoding, location, reason = encode_enrollment_face(recognizer_factory(), astronaut_rgb)
    assert encoding is None and location is None
    assert "2 faces" in reason


def test_enroll_crop_then_recognize_full_photo(recognizer_factory, astronaut_rgb, astronaut_face_rgb):
    recognizer = recognizer_factory()
    encoding, _, reason = encode_enrollment_face(recognizer, astronaut_face_rgb)
    assert reason is None
    recognizer.database = FaceDatabase(["Eileen"], [encoding])

    faces = recognizer.identify(astronaut_rgb)
    face = next(f for f in faces if _face_center_in_upper_half(f))
    patch = next(f for f in faces if not _face_center_in_upper_half(f))
    assert face.name == "Eileen"
    assert face.distance < 0.3
    assert patch.name == UNKNOWN

    # Same person mirrored is still a match.
    [mirrored] = [f for f in recognizer.identify(np.ascontiguousarray(astronaut_rgb[:, ::-1])) if _face_center_in_upper_half(f)]
    assert mirrored.name == "Eileen"


def test_bgr_frame_path_matches_rgb_path(recognizer_factory, astronaut_rgb, astronaut_face_rgb):
    # 512x512 at 0.5 scale leaves her face ~45px, which HOG still finds.
    recognizer = recognizer_factory(frame_scale=0.5)
    encoding, _, _ = encode_enrollment_face(recognizer, astronaut_face_rgb)
    recognizer.database = FaceDatabase(["Eileen"], [encoding])
    faces = recognizer.identify_bgr_frame(rgb_to_bgr(astronaut_rgb))
    assert any(f.name == "Eileen" for f in faces)


def test_no_face_in_blank_or_noise_image(recognizer_factory):
    recognizer = recognizer_factory()
    assert recognizer.identify(np.zeros((300, 300, 3), np.uint8)) == []
    noise = np.random.default_rng(0).integers(0, 256, (300, 300, 3), dtype=np.uint8)
    assert recognizer.identify(noise) == []


def test_build_database_from_folder(recognizer_factory, astronaut_face_rgb, tmp_path):
    faces_dir = tmp_path / "known_faces"
    (faces_dir / "eileen").mkdir(parents=True)
    cv2.imwrite(str(faces_dir / "eileen" / "face.jpg"), rgb_to_bgr(astronaut_face_rgb))
    cv2.imwrite(str(faces_dir / "group.jpg"), cv2.imread(str(ASTRONAUT)))  # ambiguous -> skipped
    (faces_dir / "broken.jpg").write_bytes(b"not an image")

    database, report = build_database(recognizer_factory(), faces_dir, num_jitters=1)
    assert database.counts() == {"eileen": 1}
    assert report.added == {"eileen": 1}
    assert sorted(p.name for p, _ in report.skipped) == ["broken.jpg", "group.jpg"]


def test_cli_enroll_identify_list(astronaut_face_rgb, tmp_path, capsys):
    faces_dir = tmp_path / "known_faces"
    (faces_dir / "eileen").mkdir(parents=True)
    cv2.imwrite(str(faces_dir / "eileen" / "face.jpg"), rgb_to_bgr(astronaut_face_rgb))
    db_path = tmp_path / "db.npz"
    common = ["--faces-dir", str(faces_dir), "--db", str(db_path)]

    assert main(["enroll", *common, "--jitters", "1"]) == 0
    assert db_path.exists()

    out_dir = tmp_path / "out"
    assert main(["identify", str(ASTRONAUT), *common, "--out", str(out_dir)]) == 0
    output = capsys.readouterr().out
    assert "2 face(s)" in output
    assert "eileen" in output and UNKNOWN in output
    assert (out_dir / "astronaut_annotated.jpg").exists()

    assert main(["list", *common]) == 0
    assert "eileen: 1 encoding(s)" in capsys.readouterr().out

    assert main(["identify", str(tmp_path / "missing.jpg"), *common]) == 1

    # Two inputs with the same file name get separate annotated copies.
    (tmp_path / "copy").mkdir()
    shutil.copy(ASTRONAUT, tmp_path / "copy" / ASTRONAUT.name)
    assert main(["identify", str(ASTRONAUT), str(tmp_path / "copy" / ASTRONAUT.name), *common, "--out", str(out_dir)]) == 0
    assert sorted(p.name for p in out_dir.iterdir()) == ["astronaut_annotated.jpg", "astronaut_annotated_2.jpg"]


def test_identify_auto_builds_missing_database(astronaut_face_rgb, tmp_path, capsys):
    faces_dir = tmp_path / "known_faces"
    (faces_dir / "eileen").mkdir(parents=True)
    cv2.imwrite(str(faces_dir / "eileen" / "face.jpg"), rgb_to_bgr(astronaut_face_rgb))
    db_path = tmp_path / "db.npz"

    assert main(["identify", str(ASTRONAUT), "--faces-dir", str(faces_dir), "--db", str(db_path)]) == 0
    assert db_path.exists()
    assert "eileen" in capsys.readouterr().out


def test_run_live_on_video_file_headless(recognizer_factory, astronaut_rgb, astronaut_face_rgb, tmp_path):
    video_path = tmp_path / "clip.avi"
    frame = rgb_to_bgr(astronaut_rgb)
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (frame.shape[1], frame.shape[0]))
    assert writer.isOpened()
    for _ in range(6):
        writer.write(frame)
    writer.release()

    recognizer = recognizer_factory(frame_scale=0.5, process_every_n_frames=2)
    encoding, _, _ = encode_enrollment_face(recognizer, astronaut_face_rgb)
    recognizer.database = FaceDatabase(["Eileen"], [encoding])

    seen = []
    frames = run_live(recognizer, source=str(video_path), display=False, on_faces=lambda faces, _: seen.append(faces))
    assert frames == 6
    assert len(seen) == 3  # every 2nd frame
    assert all(any(f.name == "Eileen" for f in faces) for faces in seen)

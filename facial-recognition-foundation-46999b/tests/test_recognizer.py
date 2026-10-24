"""FaceRecognizer logic with face_recognition replaced by a fake (no dlib models needed)."""

from types import SimpleNamespace

import numpy as np
import pytest
from conftest import random_encoding

import facerec.recognizer as recognizer_module
from facerec import UNKNOWN, FaceConfig, FaceDatabase, FaceRecognizer


@pytest.fixture
def fake_fr(monkeypatch):
    calls = SimpleNamespace(locations=[], encodings=[])
    state = SimpleNamespace(boxes=[], encoding=random_encoding(1), calls=calls)

    def face_locations(img, number_of_times_to_upsample=1, model="hog"):
        calls.locations.append(SimpleNamespace(shape=img.shape, upsample=number_of_times_to_upsample, model=model))
        return list(state.boxes)

    def face_encodings(img, known_face_locations=None, num_jitters=1, model="small"):
        calls.encodings.append(SimpleNamespace(img=img, locations=known_face_locations, jitters=num_jitters, model=model))
        return [state.encoding for _ in known_face_locations]

    module = SimpleNamespace(face_locations=face_locations, face_encodings=face_encodings)
    monkeypatch.setattr(recognizer_module, "load_face_recognition", lambda: module)
    return state


def test_bgr_frame_detects_small_encodes_full_res(fake_fr):
    fake_fr.boxes = [(10, 40, 40, 10)]  # in quarter-size coordinates
    db = FaceDatabase(["alice"], [fake_fr.encoding])
    recognizer = FaceRecognizer(db, FaceConfig(frame_scale=0.25, upsample=2, detection_model="cnn"))

    frame = np.zeros((480, 640, 3), np.uint8)
    frame[..., 2] = 255  # pure red in BGR
    [face] = recognizer.identify_bgr_frame(frame)

    detect_call = fake_fr.calls.locations[0]
    assert detect_call.shape == (120, 160, 3)
    assert (detect_call.upsample, detect_call.model) == (2, "cnn")

    encode_call = fake_fr.calls.encodings[0]
    assert encode_call.img.shape == (480, 640, 3)  # encoded at full resolution
    assert encode_call.img.flags["C_CONTIGUOUS"]
    assert encode_call.img[0, 0].tolist() == [255, 0, 0]  # converted to RGB
    assert encode_call.locations == [(40, 160, 160, 40)]
    assert all(type(v) is int for v in encode_call.locations[0])  # dlib.rectangle wants plain ints

    assert face.name == "alice"
    assert face.location == (40, 160, 160, 40)
    assert face.is_known


def test_identify_detects_large_photos_downscaled(fake_fr):
    fake_fr.boxes = [(100, 400, 400, 100)]  # in the 1600px-wide detection copy
    recognizer = FaceRecognizer(config=FaceConfig(max_image_size=1600))
    [face] = recognizer.identify(np.zeros((2400, 3200, 3), np.uint8))
    assert fake_fr.calls.locations[0].shape == (1200, 1600, 3)
    assert fake_fr.calls.encodings[0].img.shape == (2400, 3200, 3)
    assert face.location == (200, 800, 800, 200)  # reported in original pixels


def test_encode_accepts_non_contiguous_views(fake_fr):
    recognizer = FaceRecognizer()
    view = np.zeros((50, 50, 3), np.uint8)[:, ::-1]
    recognizer.encode(view, [(5, 20, 20, 5)])
    assert fake_fr.calls.encodings[0].img.flags["C_CONTIGUOUS"]


def test_recognized_faces_compare_without_encoding(fake_fr):
    fake_fr.boxes = [(5, 20, 20, 5)]
    recognizer = FaceRecognizer()
    image = np.zeros((50, 50, 3), np.uint8)
    first, second = recognizer.identify(image), recognizer.identify(image)
    assert first == second  # numpy encodings would make == raise if compared


def test_full_scale_skips_resize(fake_fr):
    fake_fr.boxes = [(1, 2, 3, 1)]
    recognizer = FaceRecognizer(config=FaceConfig(frame_scale=1.0))
    recognizer.identify_bgr_frame(np.zeros((50, 60, 3), np.uint8))
    assert fake_fr.calls.locations[0].shape == (50, 60, 3)


def test_identify_unknown_and_no_faces(fake_fr):
    recognizer = FaceRecognizer(FaceDatabase(["bob"], [random_encoding(2)]))
    assert recognizer.identify(np.zeros((50, 50, 3), np.uint8)) == []
    assert fake_fr.calls.encodings == []  # no encode call when nothing was detected

    fake_fr.boxes = [(5, 20, 20, 5)]
    [face] = recognizer.identify(np.zeros((50, 50, 3), np.uint8))
    assert face.name == UNKNOWN
    assert not face.is_known


def test_encode_uses_config_and_override(fake_fr):
    recognizer = FaceRecognizer(config=FaceConfig(num_jitters=3, encoding_model="large"))
    image = np.zeros((50, 50, 3), np.uint8)
    recognizer.encode(image, [(5, 20, 20, 5)])
    recognizer.encode(image, [(5, 20, 20, 5)], num_jitters=7)
    assert [(c.jitters, c.model) for c in fake_fr.calls.encodings] == [(3, "large"), (7, "large")]


@pytest.mark.parametrize(
    "bad",
    [
        {"tolerance": 0},
        {"tolerance": 1.5},
        {"detection_model": "yolo"},
        {"encoding_model": "medium"},
        {"frame_scale": 0},
        {"num_jitters": 0},
        {"process_every_n_frames": 0},
        {"upsample": -1},
        {"max_image_size": 10},
    ],
)
def test_config_validation(bad):
    with pytest.raises(ValueError):
        FaceConfig(**bad)


def test_locate_handles_thin_and_empty_images(fake_fr):
    recognizer = FaceRecognizer(config=FaceConfig(max_image_size=1600))
    assert recognizer.identify(np.zeros((1, 4000, 3), np.uint8)) == []  # short side would round to 0
    assert fake_fr.calls.locations[0].shape == (1, 1600, 3)
    assert recognizer.identify(np.zeros((0, 0, 3), np.uint8)) == []
    assert recognizer.identify_bgr_frame(np.zeros((1, 640, 3), np.uint8)) == []


def test_max_image_size_zero_detects_at_full_resolution(fake_fr):
    recognizer = FaceRecognizer(config=FaceConfig(max_image_size=0))
    recognizer.identify(np.zeros((3000, 4000, 3), np.uint8))
    assert fake_fr.calls.locations[0].shape == (3000, 4000, 3)


def test_max_image_size_auto_depends_on_detector(fake_fr):
    image = np.zeros((3000, 4000, 3), np.uint8)
    FaceRecognizer(config=FaceConfig()).identify(image)
    FaceRecognizer(config=FaceConfig(detection_model="cnn")).identify(image)
    assert [c.shape for c in fake_fr.calls.locations] == [(3000, 4000, 3), (1200, 1600, 3)]

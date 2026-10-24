import numpy as np
import pytest
from PIL import Image

from facerec.imaging import bgr_to_rgb, box_area, load_image, scale_location, to_rgb


def test_bgr_to_rgb_swaps_channels_and_is_contiguous():
    frame = np.zeros((4, 6, 3), np.uint8)
    frame[..., 0] = 10  # B
    frame[..., 2] = 200  # R
    rgb = bgr_to_rgb(frame)
    assert rgb[0, 0].tolist() == [200, 0, 10]
    assert rgb.flags["C_CONTIGUOUS"]


def test_to_rgb_normalizes_inputs():
    gray = np.full((5, 5), 7, np.uint8)
    assert to_rgb(gray).shape == (5, 5, 3)
    rgba = np.zeros((5, 5, 4), np.uint8)
    assert to_rgb(rgba).shape == (5, 5, 3)
    flipped_view = np.zeros((5, 5, 3), np.uint8)[:, :, ::-1]
    assert not flipped_view.flags["C_CONTIGUOUS"]
    assert to_rgb(flipped_view).flags["C_CONTIGUOUS"]


@pytest.mark.parametrize("bad", [np.zeros((5, 5, 3), np.float32), np.zeros((5, 5, 2), np.uint8)])
def test_to_rgb_rejects_bad_images(bad):
    with pytest.raises(ValueError):
        to_rgb(bad)


def test_scale_location_scales_and_clips():
    assert scale_location((10, 40, 30, 5), 4, 4, (480, 640, 3)) == (40, 160, 120, 20)
    # Clipped to the image bounds.
    assert scale_location((-2, 170, 130, -1), 4, 4, (480, 640, 3)) == (0, 640, 480, 0)


def test_box_area():
    assert box_area((10, 30, 20, 10)) == 200
    assert box_area((20, 30, 10, 10)) == 0


def test_load_image_applies_exif_rotation(tmp_path):
    # A 40x20 (landscape) image tagged "rotate 90 CW" must load as 20x40 (portrait),
    # the way phones store portrait photos.
    image = Image.new("RGB", (40, 20), (255, 0, 0))
    exif = image.getexif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW
    path = tmp_path / "rotated.jpg"
    image.save(path, exif=exif)

    loaded = load_image(path)
    assert loaded.shape == (40, 20, 3)
    assert loaded.dtype == np.uint8
    assert loaded.flags["C_CONTIGUOUS"]


def test_load_image_max_size_and_mode(tmp_path):
    path = tmp_path / "big.png"
    Image.new("RGBA", (400, 100)).save(path)
    loaded = load_image(path, max_size=200)
    assert loaded.shape == (50, 200, 3)


def test_load_image_too_large_is_value_error(tmp_path, monkeypatch):
    path = tmp_path / "big.png"
    Image.new("RGB", (100, 100)).save(path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # 100x100 is > 2x this: a "decompression bomb"
    with pytest.raises(ValueError, match="too large"):
        load_image(path)

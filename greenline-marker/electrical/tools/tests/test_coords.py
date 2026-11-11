"""The single design <-> KiCad coordinate conversion."""
import math

import pytest

from gleda import coords


def test_y_axis_is_flipped_and_origin_offset():
    ox, oy = coords.KICAD_ORIGIN_MM
    assert coords.to_kicad_mm(0, 0) == (ox, oy)
    # +y in the design is UP, i.e. a SMALLER KiCad y
    kx, ky = coords.to_kicad_mm(3.0, 5.0)
    assert kx == ox + 3.0 and ky == oy - 5.0
    assert coords.from_kicad_mm(kx, ky) == (3.0, 5.0)


def test_nm_round_trip():
    assert coords.to_kicad_nm(1.5, -2.25) == (101_500_000, 102_250_000)
    assert coords.from_kicad_nm(101_500_000, 102_250_000) == (1.5, -2.25)
    assert coords.mm_to_nm(0.127) == 127000


def test_rotation_is_counter_clockwise_in_y_up_frame():
    assert coords.rotate(1, 0, 90) == (0, 1)
    assert coords.rotate(1, 0, 180) == (-1, 0)
    assert coords.rotate(1, 0, 270) == (0, -1)
    x, y = coords.rotate(1, 0, 45)
    assert x == pytest.approx(math.sqrt(0.5)) and y == pytest.approx(math.sqrt(0.5))


def test_local_to_board_top():
    # pad at local (+1, 0), part at (10, 5) rotated 90 CCW -> pad is above the part
    assert coords.local_to_board(1, 0, 10, 5, 90, "top") == (10, 6)
    assert coords.local_to_board(0, 1, 10, 5, 0, "top") == (10, 6)


def test_local_to_board_bottom_is_kicad_flip():
    # KiCad flips about the footprint X axis: local +y ends up at board -y,
    # local +x stays at board +x (rotation 0)
    assert coords.local_to_board(1, 0, 0, 0, 0, "bottom") == (1, 0)
    assert coords.local_to_board(0, 1, 0, 0, 0, "bottom") == (0, -1)
    # then rotation CCW seen from the top
    assert coords.local_to_board(0, 1, 0, 0, 90, "bottom") == (1, 0)


@pytest.mark.parametrize("side", ["top", "bottom"])
@pytest.mark.parametrize("rot", [0, 90, 180, 270, 33.3])
def test_board_to_local_inverse(side, rot):
    bx, by = coords.local_to_board(1.2, -0.7, 4, -3, rot, side)
    lx, ly = coords.board_to_local(bx, by, 4, -3, rot, side)
    assert lx == pytest.approx(1.2) and ly == pytest.approx(-0.7)


def test_angles():
    assert coords.normalize_angle(270) == -90
    assert coords.normalize_angle(-180) == 180
    assert coords.local_angle_to_board(30, 90, "top") == 120
    assert coords.local_angle_to_board(30, 90, "bottom") == 60
    assert coords.to_kicad_angle(45) == 45.0


def test_flip_layer():
    assert coords.flip_layer("F.Cu") == "B.Cu"
    assert coords.flip_layer("B.Mask") == "F.Mask"
    assert coords.flip_layer("In1.Cu") == "In1.Cu"

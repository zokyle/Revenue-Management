"""Custom footprint generators and KiCad library wrappers."""
import os

import pytest

from gleda import footprints as F


def _pads(spec):
    return {p.number: p for p in spec.pads}


def test_castellated_module_geometry():
    m = F.castellated_module("Mod_10x15.5", 10.0, 15.5, pitch=0.6, left=20, bottom=14,
                             right=20, pad_w=0.3, inset=0.6, overhang=0.4,
                             under_pads=[("55", -1.5, 0, 1.2, 1.2), ("55", 1.5, 0, 1.2, 1.2)],
                             height=2.0)
    assert len(m.pads) == 56
    assert m.pad_numbers() == [str(i) for i in range(1, 56)]
    p = _pads(m)
    # counter-clockwise numbering starting at the top-left corner (+y is up)
    assert p["1"].x == pytest.approx(-4.9) and p["1"].y == pytest.approx(5.7)
    assert p["20"].y == pytest.approx(-5.7) and p["20"].x == p["1"].x      # down the left
    assert p["21"].y == pytest.approx(-7.65) and p["21"].x == pytest.approx(-3.9)
    assert p["34"].x == pytest.approx(3.9)                                  # along the bottom
    assert p["35"].x == pytest.approx(4.9) and p["35"].y == pytest.approx(-5.7)
    assert p["54"].y == pytest.approx(5.7)                                  # up the right
    # pitch and pad size / orientation
    assert p["1"].y - p["2"].y == pytest.approx(0.6)
    assert p["22"].x - p["21"].x == pytest.approx(0.6)
    assert (p["1"].w, p["1"].h) == (1.0, 0.3)          # long axis across the left edge
    assert (p["21"].w, p["21"].h) == (0.3, 1.0)
    # each edge pad reaches `overhang` outside and `inset` under the body
    assert p["1"].x - p["1"].w / 2 == pytest.approx(-5.0 - 0.4)
    assert p["1"].x + p["1"].w / 2 == pytest.approx(-5.0 + 0.6)
    assert p["21"].y - p["21"].h / 2 == pytest.approx(-7.75 - 0.4)
    # courtyard encloses pads + body with margin, body is the module outline
    assert m.body_bbox() == (-5.0, -7.75, 5.0, 7.75)
    cx0, cy0, cx1, cy1 = m.courtyard_bbox()
    assert cx0 <= -5.4 - 0.25 + 1e-9 and cy0 <= -8.15 - 0.25 + 1e-9
    assert cy1 >= 7.75 + 0.25 - 1e-9
    assert m.smd and m.lib_id == "gleda:Mod_10x15.5"


def test_castellated_module_offsets_and_errors():
    m = F.castellated_module("M", 8, 8, pitch=1.0, left=3, offsets={"left": 1.0})
    ys = [p.y for p in m.pads]
    assert ys == pytest.approx([3.0, 2.0, 1.0])
    with pytest.raises(ValueError):
        F.castellated_module("M", 8, 8, pitch=1.0, left=20)       # does not fit
    with pytest.raises(ValueError):
        F.castellated_module("M", 8, 8, pitch=1.0)                # no pads


def test_fpc_connector_generator():
    c = F.fpc_connector("FPC24", 24, pitch=0.5)
    signal = [p for p in c.pads if p.number != "MP"]
    assert [p.number for p in signal] == [str(i) for i in range(1, 25)]
    assert signal[0].x == pytest.approx(-5.75) and signal[-1].x == pytest.approx(5.75)
    assert signal[1].x - signal[0].x == pytest.approx(0.5)
    assert len([p for p in c.pads if p.number == "MP"]) == 2
    assert c.pad_numbers()[-1] == "MP"


def test_quad_package_generator():
    q = F.quad_package("LGA14", 2.5, 3.0, pitch=0.5, nx=3, ny=4, pad_w=0.25, pad_l=0.475)
    assert len(q.pads) == 14
    p = _pads(q)
    assert p["1"].x < 0 and p["1"].y == pytest.approx(0.75)        # top-left, going down
    assert p["4"].y == pytest.approx(-0.75)
    assert p["5"].y < 0 and p["5"].x == pytest.approx(-0.5)        # bottom row, left->right
    assert p["8"].x > 0 and p["8"].y == pytest.approx(-0.75)       # right side, going up
    assert p["12"].y > 0 and p["12"].x == pytest.approx(0.5)       # top row, right->left
    ep = F.quad_package("QFN", 3, 3, pitch=0.5, nx=4, ny=4, pad_w=0.25, pad_l=0.8,
                        ep=(1.7, 1.7))
    assert ep.pads[-1].number == "17" and ep.pads[-1].w == 1.7


def test_simple_pad_footprints():
    tp = F.test_pad(1.0)
    assert tp.pads[0].kind == "conn" and tp.pads[0].shape == "circle"
    assert tp.exclude_from_bom and tp.exclude_from_pos
    bt = F.battery_tab(2.0, 3.0)
    assert bt.pads[0].kind == "smd" and bt.pads[0].shape == "rect"
    row = F.pad_row("Pogo4", 4, 1.27, 0.9)
    assert [p.x for p in row.pads] == pytest.approx([-1.905, -0.635, 0.635, 1.905])
    hole = F.npth_hole(1.6)
    assert hole.pads[0].kind == "npth" and hole.pads[0].drill == 1.6 and hole.board_only


def test_pad_spec_validation():
    with pytest.raises(ValueError):
        F.PadSpec("1", 0, 0, 1, 1, shape="star")
    with pytest.raises(ValueError):
        F.PadSpec("1", 0, 0, 1, 1, kind="th")              # no drill
    with pytest.raises(ValueError):
        F.PadSpec("1", 0, 0, 0, 1)
    assert F.PadSpec("1", 1, 1, 2, 1, rotation=90).bbox() == pytest.approx((0.5, 0, 1.5, 2))


def test_kicad_mod_text_flips_y_and_controls_paste_mask():
    spec = F.FootprintSpec("T", [
        F.PadSpec("1", 1.0, 2.0, 0.5, 0.3),
        F.PadSpec("2", -1.0, -2.0, 0.5, 0.3, kind="conn"),
        F.PadSpec("3", 0.0, 0.0, 0.5, 0.3, paste=False, mask_margin=0.05,
                  paste_margin=-0.02, shape="roundrect", rotation=45),
        F.PadSpec("", 3.0, 0.0, 1.0, 1.0, shape="circle", kind="npth", drill=1.0),
    ], body=(4, 5), pin1=(-2.5, 2.0))
    text = F.kicad_mod_text(spec)
    assert text == F.kicad_mod_text(spec)                        # deterministic
    # design +y (up) becomes KiCad -y
    assert '(pad "1" smd rect (at 1 -2) (size 0.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask"))' in text
    assert '(pad "2" connect rect (at -1 2) (size 0.5 0.3) (layers "F.Cu" "F.Mask"))' in text
    assert '(pad "3" smd roundrect (at 0 0 45) (size 0.5 0.3) (layers "F.Cu" "F.Mask") ' \
           '(roundrect_rratio 0.25) (solder_mask_margin 0.05) (solder_paste_margin -0.02))' in text
    assert '(pad "" np_thru_hole circle (at 3 0) (size 1 1) (drill 1) (layers "*.Cu" "*.Mask"))' \
        in text
    assert '"F.CrtYd"' in text and '"F.Fab"' in text and '"F.SilkS"' in text
    assert 'fp_text reference "REF**"' in text


def test_silk_outline_avoids_pads():
    m = F.castellated_module("M", 6, 6, pitch=1.0, left=4, right=4)
    segs = F._silk_segments(m)
    assert segs, "top/bottom edges are free and must carry silk"
    grow = 0.15 + 0.06
    for (x0, y0), (x1, y1) in segs:
        for p in m.pads:
            bx0, by0, bx1, by1 = p.bbox()
            # no silk segment end point inside a (grown) pad
            for x, y in ((x0, y0), (x1, y1), ((x0 + x1) / 2, (y0 + y1) / 2)):
                assert not (bx0 - grow + 1e-9 < x < bx1 + grow - 1e-9
                            and by0 - grow + 1e-9 < y < by1 + grow - 1e-9)


def test_write_library_and_name_clash(tmp_path):
    a = F.test_pad(1.0)
    b = F.smd_pad("TestPad_D1mm", 2.0)                # same name, different content
    lib = str(tmp_path / "gleda.pretty")
    out = F.write_library([a, a], lib)
    assert os.path.exists(out["TestPad_D1mm"])
    with pytest.raises(F.FootprintError):
        F.write_library([a, b], lib)


def test_resolve_custom_spec_matches_spec():
    m = F.castellated_module("Mod_res", 7.0, 9.0, pitch=0.8, left=8, bottom=4, right=8,
                             pad_w=0.4, inset=0.6, overhang=0.3,
                             under_pads=[("21", -1, 0, 1, 1), ("21", 1, 0, 1, 1)], height=1.8)
    geom = F.resolve(m)
    assert geom.lib_id == "gleda:Mod_res"
    assert len(geom.pads) == len(m.pads) == 22
    by_num = {}
    for pg in geom.pads:
        by_num.setdefault(pg.number, []).append(pg)
    for ps in m.pads:
        match = [pg for pg in by_num[ps.number]
                 if abs(pg.x - ps.x) < 1e-6 and abs(pg.y - ps.y) < 1e-6]
        assert match, "pad %s not found at its spec position (+y up)" % ps.number
        pg = match[0]
        assert (pg.w, pg.h) == pytest.approx((ps.w, ps.h))
        assert pg.kind == "smd" and pg.layers == ("F.Cu", "F.Paste", "F.Mask")
        xs = [q[0] for q in pg.polygon]
        ys = [q[1] for q in pg.polygon]
        assert (min(xs), min(ys), max(xs), max(ys)) == pytest.approx(ps.bbox(), abs=1e-6)
    assert geom.body == pytest.approx((-3.5, -4.5, 3.5, 4.5))
    assert geom.courtyard == pytest.approx(m.courtyard_bbox(), abs=1e-4)
    assert geom.height == 1.8 and geom.smd and geom.has_courtyard
    assert F.resolve(m) is geom                         # cached


def test_resolve_library_footprints():
    c = F.resolve("Capacitor_SMD:C_0402_1005Metric")
    assert c.pad_numbers == ["1", "2"]
    assert c.pads[0].x == pytest.approx(-0.48) and c.pads[1].x == pytest.approx(0.48)
    assert c.body == pytest.approx((-0.5, -0.25, 0.5, 0.25))
    assert c.courtyard == pytest.approx((-0.91, -0.46, 0.91, 0.46), abs=1e-3)
    assert c.pads[0].shape == "roundrect" and len(c.pads[0].polygon) > 4
    lga = F.resolve("Package_LGA:Bosch_LGA-14_3x2.5mm_P0.5mm")
    assert len(lga.pad_numbers) == 14
    # KiCad draws pin 1 at the top-left: in +y-up coordinates that is +y
    assert lga.pads_numbered("1")[0].x < 0 and lga.pads_numbered("1")[0].y > 0
    fpc = F.resolve("Connector_FFC-FPC:Hirose_FH12-24S-0.5SH_1x24-1MP_P0.50mm_Horizontal")
    assert fpc.pad_numbers[-1] == "MP" and len(fpc.pads_numbered("MP")) == 2
    assert len(fpc.pad_numbers) == 25


def test_resolve_through_hole_and_npth():
    hdr = F.resolve("Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
    assert not hdr.smd
    assert hdr.pads[0].kind == "th" and hdr.pads[0].drill == pytest.approx(1.0)
    assert "F.Cu" in hdr.pads[0].layers and "B.Cu" in hdr.pads[0].layers
    # pad 2 is BELOW pad 1 on screen in KiCad => negative y in the +y-up frame
    assert hdr.pads_numbered("2")[0].y == pytest.approx(-2.54)
    hole = F.resolve(F.npth_hole(1.6))
    assert hole.pads[0].kind == "npth" and hole.pads[0].drill == pytest.approx(1.6)
    assert hole.pad_numbers == []


def test_missing_footprints_raise():
    with pytest.raises(F.FootprintError):
        F.resolve("Capacitor_SMD:Does_Not_Exist")
    with pytest.raises(F.FootprintError):
        F.resolve("No_Such_Library:Thing")
    with pytest.raises(F.FootprintError):
        F.resolve("NoColon")


def test_load_sets_library_link(tmp_path):
    fp = F.load("Resistor_SMD:R_0402_1005Metric")
    assert str(fp.GetFPID().GetUniStringLibId()) == "Resistor_SMD:R_0402_1005Metric"
    lib = str(tmp_path / "gleda.pretty")
    fp2 = F.load(F.test_pad(1.2), custom_lib_dir=lib)
    assert str(fp2.GetFPID().GetUniStringLibId()) == "gleda:TestPad_D1.2mm"
    assert os.path.exists(os.path.join(lib, "TestPad_D1.2mm.kicad_mod"))


def test_castellated_board_edge_pad_loads_in_kicad():
    """kind="castellated": plated half-hole for when THIS board is the module."""
    spec = F.FootprintSpec("EdgeCastellation", [
        F.PadSpec("1", 0.0, 0.0, 1.0, 1.0, shape="oval", kind="castellated", drill=0.6),
        F.PadSpec("2", 1.27, 0.0, 1.0, 1.0, shape="circle", kind="th", drill=0.6),
    ], body=(2.5, 1.0), body_offset=(0.635, 0.0), silk=False)
    text = F.kicad_mod_text(spec)
    assert "(property pad_prop_castellated)" in text and "(attr through_hole)" in text
    geom = F.resolve(spec)
    assert [p.kind for p in geom.pads] == ["th", "th"]
    assert geom.pads[0].drill == pytest.approx(0.6) and not geom.smd
    assert "B.Cu" in geom.pads[0].layers


def test_test_pad_is_not_collected_by_pytest():
    assert F.test_pad.__test__ is False and F.pogo_pad is F.test_pad


# -- BGA, two-pad parts, pad clearance override ---------------------------------

def test_bga_generator_names_and_positions():
    spec = F.bga("BGA25", 5, 5, pitch=0.5, pad_d=0.23, body=(3.47, 2.95), height=2.76)
    assert len(spec.pads) == 25 and spec.smd and spec.height == 2.76
    pads = {p.number: p for p in spec.pads}
    # A1 is the TOP-LEFT ball seen from the top of the board (+y up)
    assert (pads["A1"].x, pads["A1"].y) == (-1.0, 1.0)
    assert (pads["A5"].x, pads["A5"].y) == (1.0, 1.0)
    assert (pads["E1"].x, pads["E1"].y) == (-1.0, -1.0)
    assert (pads["C3"].x, pads["C3"].y) == (0.0, 0.0)
    assert all(p.shape == "circle" and p.w == p.h == 0.23 and p.kind == "smd"
               and p.clearance is None for p in spec.pads)
    assert spec.body_bbox() == (-1.735, -1.475, 1.735, 1.475)
    assert spec.pin1[0] < -1.735 and spec.pin1[1] > 0          # marker at the A1 corner
    assert "BGA-25 5x5, pitch 0.5 mm, pad 0.23 mm" in spec.description
    # default body: the ball field plus one pitch
    assert F.bga("B", 4, 3, pitch=0.8, pad_d=0.4).body == (3.2, 2.4)


def test_bga_row_letters_skip_i_o_q_s_x_z():
    assert [F.bga_row_name(i) for i in range(9)] == list("ABCDEFGHJ")
    assert F.bga_row_name(19) == "Y" and F.bga_row_name(20) == "AA"
    assert F.bga_row_name(21) == "AB"
    big = F.bga("BIG", 2, 22, pitch=0.5, pad_d=0.25)
    assert [p.number for p in big.pads[-4:]] == ["AA1", "AA2", "AB1", "AB2"]
    assert not any(ch in "IOQSXZ" for p in big.pads for ch in p.number)


def test_bga_omit_and_errors():
    spec = F.bga("BGA_OMIT", 3, 3, pitch=0.5, pad_d=0.25, omit=["b2"])
    assert len(spec.pads) == 8 and "B2" not in spec.pad_numbers()
    with pytest.raises(ValueError, match="unknown ball"):
        F.bga("X", 3, 3, pitch=0.5, pad_d=0.25, omit=["D4"])
    with pytest.raises(ValueError, match="smaller than the pitch"):
        F.bga("X", 3, 3, pitch=0.5, pad_d=0.5)
    with pytest.raises(ValueError):
        F.bga("X", 0, 3, pitch=0.5, pad_d=0.25)
    with pytest.raises(ValueError, match="every ball"):
        F.bga("X", 1, 1, pitch=0.5, pad_d=0.25, omit=["A1"])


def test_pad_clearance_override_round_trip():
    spec = F.bga("BGA_CLR", 2, 2, pitch=0.5, pad_d=0.23, pad_clearance=0.09,
                 mask_margin=0.03, paste_margin=-0.01)
    text = F.kicad_mod_text(spec)
    assert text.count("(clearance 0.09)") == 4
    assert text.count("(solder_mask_margin 0.03)") == 4
    assert text.count("(solder_paste_margin -0.01)") == 4
    geom = F.resolve(spec)                                   # read back through pcbnew
    assert [p.clearance for p in geom.pads] == [0.09] * 4
    assert geom.pads[0].number == "A1" and (geom.pads[0].x, geom.pads[0].y) == (-0.25, 0.25)
    assert F.resolve("Capacitor_SMD:C_0402_1005Metric").pads[0].clearance is None
    with pytest.raises(ValueError, match="clearance override"):
        F.PadSpec("1", 0, 0, 1, 1, clearance=0.0)


def test_two_pad_generator():
    spec = F.two_pad("PD_4.8x2.5", pad_w=1.0, pad_h=1.8, pitch=3.8, body=(4.8, 2.5),
                     numbers=("A", "K"), height=0.48, polarised=True)
    assert [(p.number, p.x, p.y, p.w, p.h) for p in spec.pads] == [
        ("A", -1.9, 0.0, 1.0, 1.8), ("K", 1.9, 0.0, 1.0, 1.8)]
    assert spec.pin1 == (-1.9 - 0.5 - 0.35, 0.0) and spec.body == (4.8, 2.5)
    geom = F.resolve(spec)
    assert geom.pad_numbers == ["A", "K"] and geom.body == (-2.4, -1.25, 2.4, 1.25)
    bare = F.two_pad("Contacts", pad_w=1.5, pad_h=2.5, pitch=4.0, paste=False)
    assert all(p.kind == "conn" for p in bare.pads) and bare.pin1 is None
    assert "F.Paste" not in F.kicad_mod_text(bare)
    with pytest.raises(ValueError, match="overlap"):
        F.two_pad("X", pad_w=2.0, pad_h=1.0, pitch=1.5)


def test_bare_pad_row_on_the_bottom_side():
    """Flush contact pads: copper + mask opening, no paste, not in BOM / PnP."""
    spec = F.pad_row("Row7", 7, 2.54, 1.8)
    assert [p.x for p in spec.pads] == pytest.approx([-7.62, -5.08, -2.54, 0, 2.54, 5.08, 7.62])
    assert all(p.kind == "conn" and p.shape == "circle" and p.w == 1.8 for p in spec.pads)
    assert spec.exclude_from_bom and spec.exclude_from_pos and not spec.silk
    from gleda.model import Design, Circle, Part, n_pin, BOTTOM
    from gleda import geometry
    d = Design("row", Circle(0, 0, 12))
    d.add(Part("J2", "pads", spec, pins=n_pin(7), x=0.0, y=-5.0, side=BOTTOM, in_bom=False))
    pads = geometry.part_pads(d, d.part("J2"))
    # flipping to the bottom keeps x: pad 1 stays at -x as seen from the TOP
    assert [(p.number, round(p.x, 2)) for p in pads][0] == ("1", -7.62)
    assert all(p.layers == ("B.Cu",) and p.y == pytest.approx(-5.0) for p in pads)

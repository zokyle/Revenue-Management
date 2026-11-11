"""kicad-cli helpers: SVG reader used by the orientation checks."""
import pytest

from gleda import kicad_cli as K

SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" viewBox="0.0000 0.0000 20.0000 10.0000">
<title>SVG Image created as x.svg date 2026/01/01 00:00:00 </title>
<g style="fill:#C83434; fill-opacity:1.0; stroke:#C83434;">
<path style="fill:#C83434;" d="M 1.0000,2.0000
3.0000,2.0000
3.0000,4.0000
Z" />
<circle cx="10.0000" cy="5.0000" r="0.5000" />
</g>
<g style="fill:#D0D2CD; fill-opacity:0.0; stroke:#D0D2CD;">
<path d="M15.0000 5.0000 A2.0000 2.0000 0.0 1 0 19.0000 5.0000" />
<rect x="0.5" y="0.5" width="1.0" height="2.0" />
</g>
</svg>
"""


def test_svg_viewbox():
    assert K.svg_viewbox(SVG) == (0.0, 0.0, 20.0, 10.0)
    with pytest.raises(ValueError):
        K.svg_viewbox("<svg></svg>")


def test_svg_elements_and_colours():
    els = K.svg_elements(SVG)
    assert [(c, k) for c, k, _ in els] == [
        ("#C83434", "path"), ("#C83434", "circle"), ("#D0D2CD", "path"), ("#D0D2CD", "rect")]
    assert els[0][2] == (1.0, 2.0, 3.0, 2.0, 3.0, 4.0)
    assert els[1][2] == (10.0, 5.0, 0.5)


def test_svg_bboxes_follow_arcs():
    boxes = K.svg_color_bboxes(SVG)
    assert boxes["#C83434"] == pytest.approx((1.0, 2.0, 10.5, 5.5))
    # half circle of radius 2 from (15,5) to (19,5): the bulge counts, and the
    # rect extends the box to the left/top
    x0, y0, x1, y1 = boxes["#D0D2CD"]
    assert (x0, y0, x1) == pytest.approx((0.5, 0.5, 19.0))
    assert y1 == pytest.approx(7.0, abs=0.02) or y1 == pytest.approx(5.0, abs=0.02)
    ys = [v for v in K.svg_elements(SVG)[2][2][1::2]]
    assert max(abs(y - 5.0) for y in ys) == pytest.approx(2.0, abs=0.02)


def test_path_parser_rejects_relative_commands():
    with pytest.raises(ValueError):
        K._path_points("m 1,1 l 2,2")


def test_run_kicad_cli_failure_is_an_exception(tmp_path):
    with pytest.raises(K.KicadCliError):
        K.run_kicad_cli(["pcb", "export", "svg", "--layers", "F.Cu", "--output",
                         str(tmp_path / "x.svg"), str(tmp_path / "missing.kicad_pcb")])

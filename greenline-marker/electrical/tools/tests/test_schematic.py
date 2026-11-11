"""Schematic generator: symbols, layout, KiCad file output and the netlist
round trip (KiCad's own netlist of the generated sheets must equal the design
model's connectivity exactly)."""
import json
import os
import re
import sys

import pytest

from gleda import board, schematic
from gleda.model import Design, Outline, Circle, Part, two_pin, n_pin

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(TOOLS, "demo")


def _design(name="sch"):
    return Design(name, Outline(Circle(0, 0, 20)), title="schematic test", revision="B",
                  company="GreenLine")


def _ic_design():
    """One IC with every pin type, a multi-pad pin and decoupling."""
    d = _design()
    pins = {"VIN": ("1", "power_in"), "GND": ("2", "power_in"), "EN": ("3", "input"),
            "NC": ("4", "nc"), "VOUT": ("5", "power_out")}
    d.add(Part("U1", "LDO-3V0", SOT235, pins=pins, mpn="LDO123", x=0, y=0, group="power"))
    d.add(Part("C1", "1u", C0402, pins=two_pin(), mpn="CAP1", x=3, y=0, group="power"))
    d.add(Part("C2", "1u", C0402, pins=two_pin(), mpn="CAP1", x=-3, y=0, group="power"))
    d.add(Part("R1", "100k", R0402, pins=two_pin(), mpn="RES1", x=0, y=3, group="power",
               dnp=True))
    d.net("VBAT", "U1.VIN", "C1.1", "R1.1", power_flag=True)
    d.net("GND", "U1.GND", "C1.2", "C2.2")
    d.net("+3V0", "U1.VOUT", "C2.1")
    d.net("EN", "U1.EN", "R1.2")
    return d


# --------------------------------------------------------------------------
# text metrics, symbols
# --------------------------------------------------------------------------

def test_text_width_is_conservative_against_kicad_font():
    import pcbnew
    b = pcbnew.BOARD()
    for text in ["CAM_PCLK_L", "V2V8_CAM", "LCD_EXTCOMIN", "GND", "+3V0", "SPI1_MISO",
                 "WWMM", "0123456789", "STM32U585RIT6", "abcxyz", "USB_DM"]:
        t = pcbnew.PCB_TEXT(b)
        t.SetText(text)
        t.SetTextSize(pcbnew.VECTOR2I(1270000, 1270000))
        t.SetTextThickness(150000)
        measured = t.GetBoundingBox().GetWidth() / 1e6
        # the estimate may be a little short for single characters but never
        # by more than the label frame allowance, and never wildly long
        assert schematic.text_width(text) >= measured - 0.9, text
        assert schematic.text_width(text) <= measured * 1.25 + 1.0, text
        assert schematic.label_length(text) * schematic.GRID >= measured + 1.5, text


def test_natural_key_and_title_split():
    refs = sorted(["R10", "R2", "C1", "R1", "U11", "U2"], key=schematic.natural_key)
    assert refs == ["C1", "R1", "R2", "R10", "U2", "U11"]
    assert schematic.split_title("short title") == ("short title", "")
    title, rest = schematic.split_title(
        "GreenLine GL-1 DEMO (toolchain proof, not the product circuit)")
    assert title == "GreenLine GL-1 DEMO" and rest.startswith("(toolchain")
    title, rest = schematic.split_title("x" * 80)
    assert len(title) == schematic.TITLE_MAX_CHARS and title + rest == "x" * 80


def test_box_symbol_puts_pins_on_the_expected_sides():
    d = _design()
    pins = {"VDD": ("1", "power_in"), "VDDIO": ("2", "power_in"),
            "GND": (("3", "4", "EP"), "power_in"), "CS": ("5", "input"),
            "SCK": ("6", "input"), "MISO": ("7", "output"), "INT": ("8", "open_drain"),
            "VREG": ("9", "power_out"), "IO1": ("10", "bidir"), "IO2": ("11", "bidir"),
            "IO3": ("12", "bidir"), "NC1": ("13", "nc")}
    d.add(Part("U7", "SENSOR-X", SOT235, pins=pins, x=0, y=0))
    d.net("GND", "U7.GND")
    d.net("+1V8", "U7.VDD", "U7.VDDIO")
    sym = schematic.make_symbol(d, d.part("U7"))
    assert sym.kind == "box"
    side = {}
    for p in sym.pins:
        side.setdefault(p.name, set()).add(p.side)
    assert side["VDD"] == {"T"} and side["VDDIO"] == {"T"}
    assert side["GND"] == {"B"}
    assert side["CS"] == {"L"} and side["SCK"] == {"L"}
    assert side["MISO"] == {"R"} and side["INT"] == {"R"} and side["VREG"] == {"R"}
    # one schematic pin per footprint pad, all with the pin's name
    assert sorted(p.number for p in sym.pins if p.name == "GND") == ["3", "4", "EP"]
    assert len(sym.pins) == 14 and len({p.number for p in sym.pins}) == 14
    # bidirectional and unused pins fill up left and right evenly
    left = [p for p in sym.pins if p.side == "L"]
    right = [p for p in sym.pins if p.side == "R"]
    assert abs(len(left) - len(right)) <= 1
    # every connection point is unique and outside the body
    x0, y0, x1, y1 = sym.box
    assert len({(p.x, p.y) for p in sym.pins}) == len(sym.pins)
    for p in sym.pins:
        assert not (x0 <= p.x <= x1 and y0 <= p.y <= y1)
    # a ground pin is recognised by its name when it has no net yet
    d2 = _design()
    d2.add(Part("U1", "X", SOT235, pins={"VSS": ("1", "power_in"), "VDD": ("2", "power_in"),
                                         "A": ("3", "input")}, x=0, y=0))
    s2 = schematic.make_symbol(d2, d2.part("U1"))
    assert {p.name: p.side for p in s2.pins} == {"VSS": "B", "VDD": "T", "A": "L"}


def test_connector_and_small_part_symbols():
    d = _design()
    d.add(Part("J1", "FPC", SOT235, pins=n_pin(5), x=0, y=0))
    d.add(Part("R1", "1k", R0402, pins=two_pin(), x=0, y=1))
    d.add(Part("C1", "1u", C0402, pins=two_pin(), x=0, y=2))
    d.add(Part("L1", "10u", R0402, pins=two_pin(), x=0, y=3))
    d.add(Part("Y1", "32k", R0402, pins=two_pin(), x=0, y=4))
    d.add(Part("D1", "LED red", R0402, pins={"K": "1", "A": "2"}, x=0, y=5))
    d.add(Part("D2", "Schottky", R0402, pins={"K": "1", "A": "2"}, x=0, y=6))
    d.add(Part("PD1", "Photodiode", R0402, pins={"A": "1", "K": "2"}, x=0, y=7))
    d.add(Part("TP1", "TP", R0402, pins={"1": "1"}, x=0, y=8))
    d.add(Part("FID1", "Thing", R0402, pins=two_pin(), x=0, y=9))
    sym = {p.ref: schematic.make_symbol(d, p) for p in d.parts}
    assert sym["J1"].kind == "box" and {p.side for p in sym["J1"].pins} == {"L"}
    assert [p.number for p in sym["J1"].pins] == ["1", "2", "3", "4", "5"]
    styles = {ref: s.style for ref, s in sym.items()}
    assert styles == {"J1": "box", "R1": "R", "C1": "C", "L1": "L", "Y1": "XTAL",
                      "D1": "LED", "D2": "D", "PD1": "PD", "TP1": "PAD", "FID1": "GEN"}
    for ref in ("D1", "D2", "PD1"):                    # anode on the left
        left = [p for p in sym[ref].pins if p.side == "L"][0]
        assert left.name == "A"
    assert sym["D1"].pins[0].number == "2" and sym["PD1"].pins[0].number == "1"
    assert sym["TP1"].kind == "one_pin" and len(sym["TP1"].pins) == 1
    # identical symbols are shared, different ones get different names
    table = schematic.SymbolTable()
    a = table.intern(schematic.make_symbol(d, d.part("R1")))
    b = table.intern(schematic.make_symbol(d, d.part("R1")))
    c = table.intern(schematic.make_symbol(d, d.part("C1")))
    assert a is b and a.name == "R" and c.name == "C"
    led_other = Part("D9", "LED red", R0402, pins={"A": "1", "K": "2"}, x=0, y=0)
    e = table.intern(schematic.make_symbol(d, d.part("D1")))
    f = table.intern(schematic.make_symbol(d, led_other), hint="D9")
    assert e.name == "LED" and f.name != "LED" and f is not e


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------

def _all_designs():
    sys.path.insert(0, DEMO)
    from demo_design import demo_design
    from dshape_design import dshape_design
    from mini_design import mini_design
    return [mini_design(), dshape_design(), demo_design()]


def test_layouts_are_free_of_overlaps_and_complete():
    for design in _all_designs():
        pages, symbols = schematic.build_pages(design)
        placed = [c.part.ref for page in pages for c in page.cells]
        assert sorted(placed) == sorted(p.ref for p in design.schematic_parts), design.name
        assert len({p.name for p in pages}) == len(pages)
        for page in pages:
            assert schematic.layout_overlaps(page) == [], (design.name, page.name)
            # every pin of every part is drawn with the pad's net (or none)
            for cell in page.cells:
                nets = design.pad_nets(cell.part.ref)
                pins = cell.pins()
                assert sorted(p.number for p in pins) == sorted(cell.part.pad_numbers())
                for p in pins:
                    assert p.net == nets.get(p.number)
                    assert p.x == int(p.x) and p.y == int(p.y)      # on the grid


def test_layout_check_detects_overlap_and_shared_points():
    d = _ic_design()
    pages, _ = schematic.build_pages(d)
    page = pages[0]
    assert schematic.layout_overlaps(page) == []
    c1 = [c for c in page.cells if c.part.ref == "C1"][0]
    c2 = [c for c in page.cells if c.part.ref == "C2"][0]
    saved = (c2.x, c2.y)
    c2.x, c2.y = c1.x, c1.y                       # exactly on top of C1
    problems = schematic.layout_overlaps(page)
    assert any("overlaps" in p for p in problems)
    assert any("share a connection point" in p for p in problems)
    c2.x, c2.y = saved[0], page.height + 20        # off the page
    assert any("outside the drawing frame" in p for p in schematic.layout_overlaps(page))
    tb = page.title_block()
    c2.x, c2.y = int(tb[0] + 15), int(tb[1] + 8)
    assert any("title block" in p for p in schematic.layout_overlaps(page))


def test_pagination_splits_a_big_group_and_shrinks_the_paper():
    d = _design("many")
    for i in range(1, 301):
        d.add(Part("R%d" % i, "10k", R0402, pins=two_pin(), x=0, y=0, group="bulk"))
        d.net("A_RATHER_LONG_NET_NAME_%d" % i, "R%d.1" % i)
        d.net("ANOTHER_LONG_NAME_%d" % i, "R%d.2" % i)
    pages, _ = schematic.build_pages(d, max_paper="A4")
    assert len(pages) > 1
    assert [p.name for p in pages][:2] == ["bulk", "bulk_2"]
    assert all(p.paper == "A4" for p in pages)
    assert sum(len(p.cells) for p in pages) == 300
    for page in pages:
        assert schematic.layout_overlaps(page) == []
    one, _ = schematic.build_pages(d, max_paper="A0")
    assert len(one) == 1 and one[0].paper != "A4"
    assert schematic.layout_overlaps(one[0]) == []
    # a small group takes the smallest paper allowed
    small, _ = schematic.build_pages(_ic_design(), max_paper="A1")
    assert [p.paper for p in small] == ["A4"]
    with pytest.raises(schematic.SchematicError):
        schematic.build_pages(d, max_paper="A4", min_paper="A3")


def test_a_part_that_cannot_fit_is_reported_not_squeezed():
    d = _design("huge")
    d.add(Part("J1", "big", SOT235, pins=n_pin(200), x=0, y=0))
    for i in range(1, 201):
        d.net("N%d" % i, "J1.%d" % i)
    with pytest.raises(schematic.SchematicError) as err:
        schematic.build_pages(d, max_paper="A4")
    assert "J1" in str(err.value) and "A4" in str(err.value)
    pages, _ = schematic.build_pages(d, max_paper="A1")
    assert len(pages) == 1 and schematic.layout_overlaps(pages[0]) == []


def test_duplicate_references_are_refused():
    d = _design()
    d.add(Part("R1", "1k", R0402, pins=two_pin(), x=0, y=0))
    d.add(Part("R1", "2k", R0402, pins=two_pin(), x=1, y=0))
    with pytest.raises(schematic.SchematicError):
        schematic.build_pages(d)


# --------------------------------------------------------------------------
# netlist parsing and comparison (no KiCad needed)
# --------------------------------------------------------------------------

NETLIST = r'''(export (version "E")
  (design (source "x.kicad_sch") (date "") (tool "Eeschema"))
  (components
    (comp (ref "R1") (value "10k") (footprint "Resistor_SMD:R_0402_1005Metric")
      (fields (field (name "MPN") "RC0402") (field (name "Note") "say \"hi\""))
      (libsource (lib "gleda") (part "R") (description ""))
      (property (name "Sheetname") (value "main")))
    (comp (ref "U1") (value "IC") (footprint "gleda:Thing")))
  (nets
    (net (code "1") (name "GND")
      (node (ref "R1") (pin "2") (pintype "passive"))
      (node (ref "U1") (pin "EP") (pinfunction "GND") (pintype "power_in")))
    (net (code "2") (name "a{slash}b")
      (node (ref "R1") (pin "1") (pintype "passive")))
    (net (code "3") (name "unconnected-(U1-NC-Pad4)")
      (node (ref "U1") (pin "4") (pintype "no_connect")))))
'''


def test_parse_sexpr_and_netlist():
    tree = schematic.parse_sexpr('(a "b c" (d 1 "q\\"x") e)')
    assert tree == ["a", "b c", ["d", "1", 'q"x'], "e"]
    with pytest.raises(ValueError):
        schematic.parse_sexpr("(a (b)")
    with pytest.raises(ValueError):
        schematic.parse_sexpr("(a))")
    nl = schematic.parse_netlist(NETLIST)
    assert set(nl.components) == {"R1", "U1"}
    assert nl.components["R1"]["fields"]["MPN"] == "RC0402"
    assert nl.components["R1"]["fields"]["Note"] == 'say "hi"'
    assert nl.components["U1"]["footprint"] == "gleda:Thing"
    assert nl.nets["GND"] == {"R1.2", "U1.EP"}
    assert nl.connected().keys() == {"GND", "a{slash}b"}
    assert nl.unconnected() == {"U1.4"}
    assert nl.pin_types["U1.EP"] == "power_in"
    with pytest.raises(ValueError):
        schematic.parse_netlist("(kicad_pcb)")
    assert schematic.kicad_unescape("a{slash}b{colon}c") == "a/b:c"


def _netlist_of(design):
    """A KicadNetlist that says exactly what the design says."""
    comps = {p.ref: {"value": p.value, "footprint": p.footprint_name,
                     "fields": {"MPN": p.mpn}} for p in design.parts}
    nets = {n: set(pads) for n, pads in design.connectivity().items()}
    connected = set().union(*nets.values())
    for part in design.parts:
        for pad in sorted(part.pad_numbers()):
            key = "%s.%s" % (part.ref, pad)
            if key not in connected:
                nets["unconnected-(%s-Pad%s)" % (part.ref, pad)] = {key}
    return schematic.KicadNetlist(comps, nets)


def test_compare_netlist_accepts_equal_and_names_every_difference():
    d = _ic_design()
    good = schematic.compare_netlist(d, _netlist_of(d))
    assert good.ok and good.problems == []
    assert (good.nets_compared, good.pads_compared, good.components_compared,
            good.unconnected_compared) == (4, 10, 4, 1)
    assert "matches" in good.summary()

    def problems(mutate):
        nl = _netlist_of(d)
        mutate(nl)
        result = schematic.compare_netlist(d, nl)
        assert not result.ok and "MISMATCH" in result.summary()
        return " | ".join(result.problems)

    def move_pad(nl):
        nl.nets["GND"].discard("C2.2")
        nl.nets["+3V0"].add("C2.2")
    text = problems(move_pad)
    assert "net GND: schematic lacks C2.2" in text and "net +3V0: schematic adds C2.2" in text

    text = problems(lambda nl: nl.nets.pop("EN"))
    assert "net EN is missing" in text

    def connect_nc(nl):
        nl.nets.pop("unconnected-(U1-Pad4)")
        nl.nets["EXTRA"] = {"U1.4"}
    text = problems(connect_nc)
    assert "extra net EXTRA" in text and "U1.4 has no net in the design" in text

    def swap_names(nl):
        nl.nets["VBAT"], nl.nets["EN"] = nl.nets["EN"], nl.nets["VBAT"]
    text = problems(swap_names)
    assert "net VBAT" in text and "net EN" in text

    def unconnect(nl):
        nl.nets["GND"].discard("C1.2")
        nl.nets["unconnected-(C1-Pad2)"] = {"C1.2"}
    text = problems(unconnect)
    assert "C1.2 is unconnected in the schematic" in text

    text = problems(lambda nl: nl.components.pop("R1"))
    assert "component R1 is missing" in text
    text = problems(lambda nl: nl.components.__setitem__(
        "R9", {"value": "1", "footprint": "x", "fields": {}}))
    assert "extra component R9" in text
    text = problems(lambda nl: nl.components["C1"].__setitem__("value", "2u2"))
    assert "C1: value" in text
    text = problems(lambda nl: nl.components["U1"].__setitem__("footprint", "Lib:Other"))
    assert "U1: footprint" in text
    text = problems(lambda nl: nl.components["U1"]["fields"].__setitem__("MPN", "other"))
    assert "U1: MPN" in text


# --------------------------------------------------------------------------
# real files through kicad-cli
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mini_sch(tmp_path_factory):
    from mini_design import mini_design
    design = mini_design()
    out = str(tmp_path_factory.mktemp("mini_sch"))
    return design, schematic.generate_schematic(design, out)


def test_generated_files_and_project(mini_sch):
    design, files = mini_sch
    assert os.path.basename(files.root) == "mini.kicad_sch"
    names = sorted(os.listdir(files.directory))
    for page in files.pages:
        assert page.filename in names
    assert {"gleda.kicad_sym", "sym-lib-table", "mini.kicad_pro"} <= set(names)
    root = open(files.root).read()
    assert root.startswith("(kicad_sch (version 20230121) (generator gleda)")
    assert root.count("(sheet (at") == len(files.pages)
    for page in files.pages:
        assert '"%s"' % page.filename in root
        text = open(os.path.join(files.directory, page.filename)).read()
        assert text.count("(symbol (lib_id") == len(page.cells)
        # every placed symbol's library symbol is embedded in the sheet
        for lib_id in set(re.findall(r'\(symbol \(lib_id "([^"]+)"\)', text)):
            assert '(symbol "%s"' % lib_id in text
    lib = open(files.symbol_library).read()
    assert lib.startswith("(kicad_symbol_lib")
    for name in files.symbols:
        assert '(symbol "%s"' % name in lib
    assert "${KIPRJMOD}/gleda.kicad_sym" in open(files.symbol_table).read()
    pro = json.load(open(files.project))
    assert pro["sheets"][0][1] == "" and [s[1] for s in pro["sheets"][1:]] == [
        p.name for p in files.pages]
    assert pro["libraries"]["pinned_symbol_libs"] == ["gleda"]
    # the board sections are the ones gleda.board writes
    want = board.project_dict(design)
    assert pro["board"] == json.loads(json.dumps(want["board"]))
    assert pro["net_settings"] == json.loads(json.dumps(want["net_settings"]))


def test_round_trip_and_pdf(mini_sch):
    design, files = mini_sch
    result = schematic.round_trip(design, files.root)
    assert result.ok, result.problems
    assert result.nets_compared == len([n for n, p in design.connectivity().items() if p])
    assert result.components_compared == len(design.parts)
    net_file = os.path.splitext(files.root)[0] + ".net"
    text = open(net_file).read()
    assert '(date "")' in text and files.directory not in text      # nothing run-specific
    pdf = schematic.export_pdf(files.root, os.path.join(files.directory, "mini.pdf"))
    assert schematic.pdf_page_count(pdf) == len(files.pages) + 1
    assert schematic.PDF_FIXED_DATE in open(pdf, "rb").read()
    pngs = schematic.pdf_to_png(pdf, os.path.join(files.directory, "mini"), dpi=40)
    assert len(pngs) == len(files.pages) + 1
    assert all(os.path.getsize(p) > 1000 for p in pngs)
    assert [os.path.basename(p) for p in pngs][:2] == ["mini-1.png", "mini-2.png"]


def test_schematic_is_deterministic(mini_sch, tmp_path):
    from mini_design import mini_design
    _design_, files = mini_sch
    again = schematic.generate_schematic(mini_design(), str(tmp_path))
    for name in sorted(os.listdir(str(tmp_path))):
        with open(os.path.join(str(tmp_path), name), "rb") as a, \
                open(os.path.join(files.directory, name), "rb") as b:
            assert a.read() == b.read(), name
    assert len(again.pages) == len(files.pages)


def test_round_trip_detects_a_tampered_sheet(tmp_path):
    design = _ic_design()
    files = schematic.generate_schematic(design, str(tmp_path))
    assert schematic.round_trip(design, files.root).ok
    sheet = files.sheets[0]
    text = open(sheet).read()
    # (1) one label renamed: the pad leaves its net and forms a new one
    assert text.count('(global_label "EN"') == 2
    with open(sheet, "w") as fh:
        fh.write(text.replace('(global_label "EN"', '(global_label "EN_X"', 1))
    result = schematic.round_trip(design, files.root)
    assert not result.ok
    joined = " | ".join(result.problems)
    assert "extra net EN_X" in joined and "net EN: schematic lacks" in joined
    # (2) a label replaced by a no-connect flag
    m = re.search(r'  \(global_label "\+3V0".*?\n  \)\n', text, re.S)
    at = re.search(r"\(at ([\d.]+) ([\d.]+) \d+\)", m.group(0))
    flag = "  (no_connect (at %s %s) (uuid 11111111-2222-3333-4444-555555555555))\n" % (
        at.group(1), at.group(2))
    with open(sheet, "w") as fh:
        fh.write(text.replace(m.group(0), flag, 1))
    result = schematic.round_trip(design, files.root)
    assert not result.ok
    assert any("is unconnected in the schematic" in p for p in result.problems)
    # (3) the untouched file passes again
    with open(sheet, "w") as fh:
        fh.write(text)
    assert schematic.round_trip(design, files.root).ok


def test_odd_net_names_and_dnp_survive_the_round_trip(tmp_path):
    d = _design("odd")
    names = ["+3V0", "~{RST}", "D[0]", "a/b", "net with space", "N$1", "A.B", "x:y",
             "MiXed-case_1", "GND"]
    for i in range(len(names)):
        d.add(Part("R%d" % (i + 1), "1k", R0402, pins=two_pin(), mpn="M%d" % i, x=0, y=i,
                   dnp=(i == 0), in_bom=(i != 1)))
    for i, name in enumerate(names):
        d.net(name, "R%d.1" % (i + 1), "R%d.2" % ((i + 1) % len(names) + 1))
    files = schematic.generate_schematic(d, str(tmp_path), project=False)
    assert files.project is None and not os.path.exists(str(tmp_path / "odd.kicad_pro"))
    result = schematic.round_trip(d, files.root)
    assert result.ok, result.problems
    text = open(files.sheets[0]).read()
    assert "(dnp yes)" in text and "(in_bom no)" in text


def test_stale_sheets_are_removed_and_project_is_merged(tmp_path):
    out = str(tmp_path)
    d = _ic_design()
    files = board.build_board(d, out)                     # writes the .kicad_pro first
    before = json.load(open(files.pro))
    # an earlier run of this design had one more group; a file of another
    # design whose name merely starts the same way is nobody's business
    earlier = _ic_design()
    earlier.add(Part("R9", "1k", R0402, pins=two_pin(), x=5, y=5, group="oldgroup"))
    earlier.net("EN", "R9.1", "R9.2")
    schematic.generate_schematic(earlier, out, project=False)
    assert os.path.exists(os.path.join(out, "sch_oldgroup.kicad_sch"))
    other = _ic_design()
    other.name = "sch_v2"
    schematic.generate_schematic(other, out, project=False)
    with open(os.path.join(out, "sch_notes.kicad_sch"), "w") as fh:
        fh.write("(kicad_sch (version 20230121) (generator eeschema))")
    sch = schematic.generate_schematic(d, out)
    assert not os.path.exists(os.path.join(out, "sch_oldgroup.kicad_sch"))
    for keep in ("sch_v2.kicad_sch", "sch_v2_power.kicad_sch", "sch_notes.kicad_sch"):
        assert os.path.exists(os.path.join(out, keep)), keep
    after = json.load(open(sch.project))
    assert after["board"] == before["board"]
    assert after["net_settings"] == before["net_settings"]
    assert after["text_variables"] == before["text_variables"]
    assert len(after["sheets"]) == 2 and after["schematic"]["meta"] == {"version": 1}
    # building the board again keeps the schematic sections
    board.build_board(d, out)
    again = json.load(open(files.pro))
    assert again["sheets"] == after["sheets"] and again["schematic"] == after["schematic"]
    assert schematic.round_trip(d, sch.root).ok


def test_demo_schematic_round_trip(tmp_path):
    sys.path.insert(0, DEMO)
    from demo_design import demo_design
    design = demo_design()
    files = schematic.generate_schematic(design, str(tmp_path))
    result = schematic.round_trip(design, files.root)
    assert result.ok, result.problems[:10]
    # the six fiducials are board-only parts: no symbols
    assert len(design.parts) - len(design.schematic_parts) == 6
    assert result.nets_compared == 72
    assert result.components_compared == len(design.schematic_parts) == 94
    # one sheet per schematic group, in the order the groups first appear
    assert [p.name for p in files.pages] == design.groups


def test_board_only_parts_have_no_symbol_and_do_not_disturb_the_round_trip(tmp_path):
    """Fiducials exist on the board only: no sheet, no symbol, and KiCad's
    netlist of the schematic still equals the design."""
    from mini_design import mini_design
    design = mini_design()
    groups = list(design.groups)
    design.add_fiducial(-11.0, -5.0)
    design.add_fiducial(11.0, 5.0, side="bottom")
    assert design.groups == groups and len(design.schematic_parts) == len(design.parts) - 2
    files = schematic.generate_schematic(design, str(tmp_path))
    text = "".join(open(p).read() for p in [files.root] + list(files.sheets))
    assert "FID1" not in text and "Fiducial" not in text
    result = schematic.round_trip(design, files.root)
    assert result.ok, result.problems
    assert result.components_compared == len(design.parts) - 2

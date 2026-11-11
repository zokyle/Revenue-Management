# gleda - GreenLine scripted EDA toolchain

`gleda` turns a "netlist as code" design description (Python) into a verified
KiCad 7 board.  KiCad's own DRC is the judge; nothing is reported as passing
unless KiCad says so.

This file documents the **core** of the toolchain (design model, checks,
footprints, board builder, DRC runner).  The router, the fabrication outputs,
the schematic generator and the demo design build on the API described here
and are documented in their own sections / module docstrings.

```
tools/
  gleda/
    model.py       design description (pure Python, no pcbnew)
    coords.py      THE design <-> KiCad coordinate conversion
    geometry.py    outline paths/polygons, placed pads, courtyards (shapely)
    footprints.py  programmatic footprints + KiCad library wrappers
    checks.py      ERC-style and placement checks
    board.py       .kicad_pcb / .kicad_pro generation, routing primitives in/out
    drc.py         zone fill + KiCad DRC + report parser + pass/fail policy
    kicad_cli.py   kicad-cli wrapper, SVG export, SVG reader
  tests/           pytest suite, mini_design.py fixture, proof_core.py
```

## Requirements

KiCad 7.0.x with its Python module.  Always use the system interpreter:

```
cd electrical/tools
/usr/bin/python3 -m pytest -q            # test suite
/usr/bin/python3 tests/proof_core.py     # build + DRC + render the mini board
/usr/bin/python3 -m gleda.drc out/board.kicad_pcb [--allow-unconnected]
```

No GUI is ever started and nothing is downloaded.

## Conventions (read this first)

* Units are millimetres.  The design origin is the **board centre**, **+x is
  right, +y is up** as seen from the top of the board; rotation is
  counter-clockwise positive.
* KiCad's y axis points down.  The conversion happens in exactly one module,
  `gleda/coords.py` (`to_kicad_mm`, `from_kicad_mm`, ...).  The board centre is
  placed at (100, 100) mm on the KiCad page and the board's auxiliary
  (drill/place) origin is set to the same point.
* Footprint-local coordinates (custom footprints, `FootprintGeom`) use the
  same handedness: +y up, looking at the component side.
* **Bottom-side parts** follow KiCad's native definition, so `Part.rotation`
  is the number KiCad stores, shows and writes to position files:
  the footprint is flipped about its local X axis and then rotated CCW as
  seen from the top:

      top:     board = (x, y) + R(rotation) . (lx,  ly)
      bottom:  board = (x, y) + R(rotation) . (lx, -ly)

  `coords.local_to_board()` implements this and
  `tests/test_board.py::test_pads_match_model_geometry` proves that every pad
  position predicted by the model equals what pcbnew reports for the saved
  board.  `tests/test_board.py::test_top_view_svg_has_plus_y_up` proves from a
  KiCad SVG plot that a part placed at +y is drawn toward the top.

## Describing a design

```python
from gleda.model import Design, Outline, Circle, RoundedPolygon, Part, two_pin, n_pin
from gleda import footprints as F

outline = Outline(Circle(0, 0, 19.0))                  # 38 mm round board
outline.add_cutout(Circle(9.0, 0.0, 6.5))              # internal routed cutout
outline.add_notch(RoundedPolygon.rect(0, -19, 3, 2, 0.4))   # crosses the edge
outline.add_slot(-6, -11, -4, -11, 0.8)
outline.add_hole(-12, 5, 1.2)                          # NPTH

d = Design("greenline", outline, layers=4, board_thickness=0.8)   # rules=US_4L_STD

module = F.castellated_module("BleModule_10x15.5", 10.0, 15.5, pitch=0.6,
                              left=20, bottom=14, right=20, height=2.0,
                              under_pads=[("55", 0, 0, 1.2, 1.2)])
d.add(Part("U1", "BLE module", module,
           pins={"GND": (("1", "20", "55"), "power_in"), "VDD": ("2", "power_in"),
                 "P0.13": ("3", "bidir"), "NC": ("4", "nc")},      # ... all pads
           mpn="...", manufacturer="...", distributor="Digi-Key", distributor_pn="...",
           unit_price=7.5, x=-4.0, y=2.0, rotation=0, side="top", height_mm=2.0,
           group="mcu"))
d.add(Part("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", pins=two_pin(),
           mpn="...", x=-10.5, y=4.0, rotation=90, group="power"))

d.net("GND", "U1.GND", "C1.2", netclass="Power")
d.net("+3V0", "U1.VDD", "C1.1", netclass="Power", power_flag=True)
d.no_connect("U1.P0.13")                               # pin names may contain dots

d.add_plane("GND", "In1.Cu")
d.add_plane("+3V0", "In2.Cu")
d.add_keepout(RoundedPolygon.rect(-4, 11, 10, 4), name="antenna")   # all layers
```

Pin shorthand accepted by `Part(pins=...)`: `"5"`, `("5", "input")`,
`(("6", "7"), "power_in")`, `["6", "7"]` or a `Pin` object.  Electrical types:
`power_in, power_out, passive, input, output, bidir, open_drain, nc`.
`pins=None` means a two-pin passive (`two_pin()`).

Per-net router options live on `Net`: `width`, `max_vias`, `layers`,
`no_route`, `priority`; `power_flag=True` marks a supply that is driven from
outside the netlist (battery tab, connector).

### Rule set

`gleda.model.Rules` is a frozen parameter object; the default instance is
`US_4L_STD`:

| rule | value |
|------|-------|
| min track / min clearance | 0.127 mm / 0.127 mm |
| via (through only) | 0.50 mm pad / 0.25 mm drill |
| min annular ring | 0.125 mm |
| hole to hole | 0.25 mm |
| hole wall to foreign copper | 0.20 mm |
| copper to board edge | 0.30 mm |
| default / power track | 0.15 mm / 0.30 mm |
| zone clearance / min width | 0.20 mm / 0.15 mm |

Use `dataclasses.replace(US_4L_STD, name="...", ...)` for another fab and pass
it to `Design(rules=...)`.  Net classes `Default` and `Power` are created from
the rules; add more with `Design.add_netclass`.

## Checks

```python
from gleda import checks
report = checks.run_checks(d)        # CheckReport
print(report.text())
report.raise_if_errors()             # CheckError if any error
report.to_dict()                     # JSON-able
```

Every finding has a severity, a machine-readable code, a message and the refs /
net involved.  The codes are listed in the `gleda/checks.py` docstring:
unconnected pins, single-pin nets, undriven power inputs, shorted outputs,
duplicate refs, pin->pad mapping vs. the real footprint, unmapped pads,
courtyard overlaps (per side; through-hole parts block both sides), parts
outside the outline / in cutouts / in keep-outs / on NPTH holes, pad copper too
close to the edge, missing decoupling capacitor on IC power pins, missing
MPN / placement, inconsistent rules.

Policy notes: ground nets (name matching GND/VSS/AGND..., or
`Design.ground_nets`) never need a power source; a pin of type `nc` is an
implicit no-connect; parts with `in_bom=False` (test pads, tabs) need no MPN;
`allow_overhang=True` exempts an edge-mounted part from the outline checks.

## Footprints

* KiCad library footprints: `"Lib:Name"` strings (searched in
  `/usr/share/kicad/footprints`, `$KICAD7_FOOTPRINT_DIR`,
  `$GLEDA_FOOTPRINT_DIRS`, `footprints.add_library_dir()`).
* Custom footprints: `FootprintSpec` objects, usually from a generator:
  `castellated_module`, `fpc_connector`, `quad_package` (LGA/QFN/DFN),
  `test_pad` / `pogo_pad`, `pad_row`, `battery_tab`, `smd_pad`, `npth_hole`,
  or hand-built from `PadSpec` (rect/roundrect/circle/oval; kinds `smd`,
  `conn` (no paste), `th`, `npth`, `castellated`; per-pad paste/mask control).
  Courtyard, fab outline, silk outline (with gaps over pads), hidden-able
  reference and pin-1 mark are generated.

Custom footprints are written as real `.kicad_mod` files into
`<out>/gleda.pretty/` (with a project `fp-lib-table`), then loaded with
pcbnew - library and custom footprints share one code path, and the project
opens in KiCad with editable footprints.

`footprints.resolve(fp)` returns a pure-Python `FootprintGeom` (pads with
copper polygons, courtyard, body box) for either kind.

## Building the board

```python
from gleda import board
files = board.build_board(d, "out")      # BoardFiles(pcb, pro, lib_dir, lib_table, directory)
```

writes `out/<name>.kicad_pcb` (stack-up, Edge.Cuts with exact arcs/circles,
NPTH holes, placed footprints with nets and BOM properties, unfilled plane
zones, keep-out rule areas), `out/<name>.kicad_pro` (design rules, net classes,
net-class assignment, DRC severities), `out/gleda.pretty/` and `fp-lib-table`.
Output is byte-for-byte reproducible.

Routing primitives:

```python
from gleda.model import Track, Via
res = board.apply_routing(files.pcb, tracks, vias)     # replace=True, strict=True
tracks, vias = board.read_routing(files.pcb)
board.board_summary(files.pcb)                         # facts read back with pcbnew
```

## DRC

```python
from gleda import drc
result = drc.run_drc(files.pcb, json_path="out/drc.json")   # fills zones, saves, runs DRC
print(result.summary())
result.errors_by_type, result.warnings_by_type, result.unconnected_count
drc.assert_clean(result)                    # DrcError unless 0 errors and 0 unconnected
drc.assert_clean(result, allow_unconnected=True)   # for boards that are not routed yet
```

Pass/fail policy (the "honesty" rules):

* Every violation of severity *error* fails, and so does every unconnected
  item.  The only violation types `assert_clean` ignores are the documented
  cosmetic ones in `drc.COSMETIC_CHECKS` (silkscreen overlap / clipping / edge
  distance, text size, footprint-library bookkeeping).  They stay in the
  result and in the JSON.
* The generated project keeps KiCad's default severities except two
  bookkeeping checks that are *warnings* by default and are set to *ignore*
  (`board.SEVERITY_OVERRIDES` records the reasons): `lib_footprint_issues`
  (a headless run has no global footprint library table, so every standard
  library is "not in the current configuration") and `lib_footprint_mismatch`
  (placed footprints differ from their library copy by a hidden reference and
  BOM properties).  No electrical or geometric check is relaxed;
  `tests/test_board.py::test_project_file_content` asserts exactly that.
* `run_drc` checks that the core checks (`board.CORE_ERROR_CHECKS`: clearance,
  track width, annular ring, drill size, hole clearance, hole-to-hole, edge
  clearance, shorts, crossing tracks, unconnected, outline, keep-out
  violations, courtyard overlap, ...) are still at severity *error* in the
  project file; if not, `DrcResult.tampered` is set and `assert_clean` fails.
* A short between two nets that both hang on pads is reported by KiCad as a
  `clearance` violation with `actual 0.0000 mm` (often together with
  `solder_mask_bridge`), not as `shorting_items`.

## pcbnew 7 gotchas the core works around

| gotcha | handling |
|--------|----------|
| `ZONE_FILLER.Fill` segfaults on a board built in memory | boards are saved, re-loaded, then filled (`drc.fill_zones`, `drc.run_drc`); the DRC job runs in a child process by default |
| `SaveBoard(path, board)` rewrites `.kicad_pro` and drops a `.kicad_prl` | `board.save_board` passes `aSkipSettings=True`; the toolchain owns the project file |
| rules / net classes are not stored in the board file | `board.write_project` writes the `.kicad_pro`; pcbnew loads it with the board |
| stack-up cannot be edited through the Python API | the `(stackup ...)` block is injected into the saved file |
| `FOOTPRINT.GetCourtyard` segfaults without a parent board; destroying a temporary BOARD that had footprints removed corrupts later `FootprintLoad` calls | one process-wide scratch board owns every inspected footprint and is never destroyed |
| KiCad sorts saved items by UUID and the footprint-library cache consumes a state-dependent number of UUIDs | the cache is warmed with throw-away loads, then `KIID.SeedGenerator` is seeded: deterministic files |
| KiCad silently merges the nets of touching tracks when the copper cluster has no pad | `board.apply_routing` compares stored nets with requested nets and raises (or reports in `ApplyResult.renetted`) |
| footprints loaded from a path have no library nickname | `footprints.load` sets `Lib:Name` / `gleda:Name` |
| KiCad 7 footprints have no DNP flag | DNP parts get `exclude_from_pos_files` and a `DNP` property |
| `kicad-cli pcb export` needs explicit layers; SVG titles carry a timestamp | `kicad_cli.export_svg` requires a layer list and rewrites the title |

## Limitations of the core

* Outline shapes: circle, rounded polygon, stadium slot.  Cutouts that cross
  the edge are resolved by a boolean operation and arcs are re-fitted (exact
  for circles known from the input shapes); free-form splines are not
  supported.
* `geometry.outline_polygon` approximates arcs to 5 um (inscribed outer
  boundary, circumscribed cutouts, i.e. always conservative).  Pad polygons
  come from KiCad and lie up to ~5 um INSIDE the true round copper; use
  `PlacedPad.inflated(distance)` (adds `geometry.PAD_POLYGON_TOLERANCE`) for
  conservative clearance shapes.
* Planes are simple filled zones (whole board or one shape), optional thermal
  reliefs; no hatched fills, no teardrops.
* Only through vias; blind/buried/micro vias are not modelled.
* Castellated *edge* pads of the board itself (`PadSpec(kind="castellated")`)
  are emitted with KiCad's castellated pad property and load in pcbnew, but no
  board with its own castellations has been taken through DRC.  Oblong (slot)
  drills are not supported in custom footprints.
* The checks are ERC-style, not a simulator: for example they cannot tell that
  a regulator's enable pin is driven to the wrong level.
* KiCad 7 only (file format 20221018).

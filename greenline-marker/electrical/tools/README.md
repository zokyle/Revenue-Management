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
    board.py       .kicad_pcb / .kicad_pro / .kicad_dru generation, routing
                   primitives in/out, via tenting
    drc.py         zone fill + KiCad DRC + report parser + pass/fail policy
    kicad_cli.py   kicad-cli wrapper, SVG export, SVG reader
  tests/           pytest suite
    mini_design.py     round 30 mm fixture (castellated module, cutout, notch, slot)
    dshape_design.py   GreenLine-shaped fixture (D outline, LQFP-64, two BGAs,
                       bottom LED ring + contact row, fine net class)
    proof_core.py      builds both, KiCad DRC, plots, orientation proof
    proof_out/         outputs of the last proof run
```

## Requirements

KiCad 7.0.x with its Python module.  Always use the system interpreter:

```
cd electrical/tools
/usr/bin/python3 -m pytest -q            # test suite
/usr/bin/python3 tests/proof_core.py     # build + DRC + render both reference boards
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
from gleda.model import (Design, Outline, Circle, RoundedPolygon, PathShape, Part,
                         two_pin, n_pin, US_4L_FINE, BOTTOM)
from gleda import footprints as F

# circle r = 21.2 mm about the origin, clipped by the chord y = +17.3 mm
outline = Outline(PathShape.d_shape(21.2, 17.3))
# also: Outline(Circle(0, 0, 19.0)), RoundedPolygon(...), any line + arc path:
#   PathShape.begin(-5, 0).line_to(5, 0).arc_to(-5, 0, 0, 0, ccw=True).close()
#   PathShape.clipped_circle(0, 0, 21.2, [(90, 17.3), (270, 19.0)])
outline.add_cutout(Circle(9.0, 0.0, 6.5))              # internal routed cutout
outline.add_notch(RoundedPolygon.rect(0, -21.2, 3, 2, 0.4))   # crosses the edge
outline.add_slot(-6, -11, -4, -11, 0.8)
outline.add_hole(-12, 5, 1.2)                          # NPTH

d = Design("greenline", outline, layers=4, rules=US_4L_FINE, board_thickness=0.8)
d.add_netclass("Fine", track_width=0.09, clearance=0.09)   # BGA escape only
d.via_tenting = "bottom"                               # "both" (default) | "bottom" | "top" | "none"

cam = F.bga("Cam_BGA25", 5, 5, pitch=0.5, pad_d=0.23, body=(3.47, 2.95), height=2.76,
            pad_clearance=0.09, courtyard_margin=0.2)
d.add(Part("U2", "Camera", cam,
           pins={"D0": ("B2", "bidir"), "AVDD": ("C5", "power_in"),
                 "GND": (("E2", "E3", "E4"), "power_in"), "NC": ("A1", "nc")},  # ... all balls
           mpn="...", manufacturer="...", distributor="Digi-Key", distributor_pn="...",
           unit_price=6.0, x=-10.2, y=15.6, rotation=0, side="top", height_mm=2.76,
           group="camera"))
d.add(Part("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", pins=two_pin(),
           mpn="...", x=-7.2, y=15.3, rotation=90, group="camera"))
d.add(Part("J2", "Cradle pads", F.pad_row("ContactRow", 7, 2.54, 1.8), pins=n_pin(7),
           x=0, y=-17.0, side=BOTTOM, in_bom=False))    # bare pads on the bottom

d.net("GND", "U2.GND", "C1.2", "J2.4", netclass="Power")
d.net("V2V8", "U2.AVDD", "C1.1", netclass="Power", power_flag=True)
d.net("CAM_D0", "U2.D0", "U1.PC6", netclass="Fine")    # inner ball: fine class
d.no_connect("U1.P0.13")                               # pin names may contain dots

d.add_plane("GND", "In1.Cu")
d.add_plane("+3V0", "In2.Cu")
d.add_body_keepout("U4")                               # no copper on F.Cu under the IMU body
d.add_keepout(RoundedPolygon.rect(0, -5.2, 34, 10), layers=("F.Cu",), name="battery",
              tracks=False, vias=False, copper=False, footprints=True)   # placement only
```

Pin shorthand accepted by `Part(pins=...)`: `"5"`, `("5", "input")`,
`(("6", "7"), "power_in")`, `["6", "7"]` or a `Pin` object.  Electrical types:
`power_in, power_out, passive, input, output, bidir, open_drain, nc`.
`pins=None` means a two-pin passive (`two_pin()`).

Per-net router options live on `Net`: `width`, `max_vias`, `layers`,
`no_route`, `priority`; `power_flag=True` marks a supply that is driven from
outside the netlist (battery tab, connector).

Tri-state outputs that share a line (camera bus, SPI MISO) must be typed
`bidir`: two `output` pins on one net are an `output_conflict` error.

### Rule set

`gleda.model.Rules` is a frozen parameter object; the default instance is
`US_4L_STD`:

| rule | `US_4L_STD` | `US_4L_FINE` |
|------|-------------|--------------|
| board minimum track / clearance | 0.127 mm / 0.127 mm | **0.09 mm / 0.09 mm** |
| via (through only) | 0.50 mm pad / 0.25 mm drill | same |
| min annular ring | 0.125 mm | same |
| hole to hole | 0.25 mm | same |
| hole wall to foreign copper | 0.20 mm | same |
| copper to board edge | 0.30 mm | same |
| default / power track | 0.15 mm / 0.30 mm | same |
| default clearance (classes Default, Power) | 0.127 mm | same |
| zone clearance / min width | 0.20 mm / 0.15 mm | same |

Use `dataclasses.replace(US_4L_STD, name="...", ...)` for another fab and pass
it to `Design(rules=...)`.

### Net classes: own track width and clearance

`Design` creates `Default` (0.15 / 0.127) and `Power` (0.30 / 0.127) from the
rules; `Design.add_netclass(name, track_width, clearance, via_diameter,
via_drill, min_track_width)` adds more, e.g. the fine class for escaping the
inner balls of a 0.5 mm-pitch BGA (needs `rules=US_4L_FINE`, otherwise the
checks report `rule_violation`).  Classes are written into the `.kicad_pro`
with one exact-match pattern per net, and KiCad reads them back
(`board.board_summary()["netclass_values"]`).

What KiCad 7's DRC actually enforces, pinned down by `tests/test_netclasses.py`
and mirrored by the model so that a router can compute the same numbers:

| question | answer | model call |
|----------|--------|------------|
| clearance between nets A and B | `max(class A clearance, class B clearance)`, never below the board minimum. A Fine track next to Default copper needs 0.127 mm | `Design.clearance(a, b)` |
| ... if one item is a pad with a local clearance override | the (larger) override replaces the class values, floor = board minimum | `Design.clearance(a, b, local_a=pad.clearance)` / `geometry.pad_clearance(design, pad, other_net)` |
| copper without a net | counts as class `Default` | `Design.clearance(a, None)` |
| track width | KiCad alone only checks the BOARD minimum. gleda writes `<name>.kicad_dru` with one `track_width` rule per class (and per net with a narrower `width` override), so 0.09 mm on a Default or Power net IS a DRC error | `Design.min_track_width(net)`, `board.custom_rules(design)` |
| nominal routing width / via | class `track_width` or the net's `width`; class via | `Design.track_width(net)`, `Design.via_size(net)` |

`NetClass.min_track_width` (below `track_width`) allows neck-downs for a class;
`Design.enforce_track_widths = False` drops the `.kicad_dru` (KiCad then only
checks the board minimum - say so in the fab notes if you use it).

`Design.board_minimums()` returns what the fab README must state: the board
minimums of the rule set (0.09 / 0.09 with `US_4L_FINE`), the smallest track /
clearance any class in use really asks for, the via, the per-class table with
net lists, and the via tenting mode.

**BGA escape arithmetic** (verified with KiCad's DRC): one track between two
adjacent pads needs `pitch - pad >= track + 2 x clearance`.  At 0.5 mm pitch a
0.09 mm track with 0.09 mm clearance needs pads of **0.23 mm or less**; with
0.25 mm pads KiCad reports `actual 0.0800 mm`.  If the neighbouring balls are
on Default-class nets, the track would need 0.127 mm to them - unless the BGA
pads carry a clearance override (`F.bga(..., pad_clearance=0.09)`), which is
the usual way to keep the fine geometry confined to the package.

### Keep-outs

`Design.add_keepout(shape, layers=ALL_LAYERS | ("F.Cu",) ..., tracks=True,
vias=True, copper=True, pads=False, footprints=False, name=...)` creates a
KiCad rule area on exactly those copper layers:

* copper keep-out on one layer only, e.g. under a MEMS sensor:
  `Design.add_body_keepout("U4")` computes the largest pad-free rectangle
  under the body (0.15 mm from the part's own pads) and forbids tracks, vias
  and pours on `F.Cu` there.  A through via crosses every layer, so a via
  keep-out on any layer blocks vias (KiCad reports `items_not_allowed`).
* placement keep-out per side: `footprints=True` with `layers=("F.Cu",)`
  rejects top-side parts only (`in_keepout`), bottom-side parts are fine.

### Via tenting

`Design.via_tenting` = `"both"` (default: vias covered by mask on both
sides), `"bottom"` (bottom tented, top open), `"top"` or `"none"`.  KiCad 7 has
no per-side tenting flag: its plots tent every via unless the global "plot
vias on mask" option is on.  gleda leaves that option off and, for every via,
draws a solder-mask opening of the via pad size on the untented side(s)
(`board.apply_routing` does this; the shapes live in the board group
`gleda_via_mask_openings` and are replaced with the routing).  The mode is
recorded in the project file (text variable `GLEDA_VIA_TENTING`).  Gerbers
must therefore be plotted WITHOUT `--board-plot-params`/"plot vias on mask";
`tests/test_dshape.py::test_via_tenting_modes` checks the mask Gerbers.
Plugging/filling of vias is a fab note, not a CAD feature.

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
close to the edge, pads of one part closer than the clearance KiCad will
require (`pad_spacing`), connected pads buried in a no-track keep-out, missing
decoupling capacitor on IC power pins, missing MPN / placement, inconsistent
rules (net class below the board minimum, bad via, bad tenting mode, names
that cannot be used in a DRC rule).

Policy notes: ground nets (name matching GND/VSS/AGND..., or
`Design.ground_nets`) never need a power source; a pin of type `nc` is an
implicit no-connect; parts with `in_bom=False` (test pads, tabs) need no MPN;
`allow_overhang=True` exempts an edge-mounted part from the outline checks.

## Footprints

* KiCad library footprints: `"Lib:Name"` strings (searched in
  `/usr/share/kicad/footprints`, `$KICAD7_FOOTPRINT_DIR`,
  `$GLEDA_FOOTPRINT_DIRS`, `footprints.add_library_dir()`).
* Custom footprints: `FootprintSpec` objects, usually from a generator:
  `bga` (A1 top-left, JEDEC row letters, optional pad clearance override),
  `castellated_module`, `fpc_connector`, `quad_package` (LGA/QFN/DFN),
  `two_pad` (photodiode, chip parts), `test_pad` / `pogo_pad`, `pad_row`
  (bare contact rows), `battery_tab`, `smd_pad`, `npth_hole`, or hand-built
  from `PadSpec` (rect/roundrect/circle/oval; kinds `smd`, `conn` (no paste),
  `th`, `npth`, `castellated`; per-pad paste/mask margins and local
  clearance).  Courtyard, fab outline, silk outline (with gaps over pads),
  hidden-able reference and pin-1 mark are generated.
* Any footprint can go on the bottom side (`Part(side="bottom")`), including
  pad-only ones: copper and mask land on `B.Cu` / `B.Mask`, x positions are
  kept, the footprint is flipped about its local X axis (KiCad's convention).

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
net-class assignment, DRC severities, tenting mode), `out/<name>.kicad_dru`
(per-class minimum track width), `out/gleda.pretty/` and `fp-lib-table`.
Output is byte-for-byte reproducible.

The toolchain owns the project file.  Other stages (schematic generator) must
not overwrite it: call `board.write_project(design, pro_path)`, which replaces
only the `board` / `net_settings` sections and keeps everything else.

Routing primitives:

```python
from gleda.model import Track, Via
res = board.apply_routing(files.pcb, tracks, vias)     # replace=True, strict=True,
                                                       # via_tenting=None (from the project)
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
* The custom rules file only ADDS constraints (minimum track width per net
  class / net).  `DrcResult.custom_rules` lists the rules KiCad applied; a
  rules file that fails to parse makes `run_drc` raise instead of passing.
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
| net-class track width is only a routing default in KiCad; DRC checks the board minimum | `board.write_custom_rules` generates `<name>.kicad_dru` (`pcbnew.LoadBoard` / `WriteDRCReport` pick it up automatically) |
| clearance between two net classes is the larger of the two; a pad's local clearance replaces both | modelled by `Design.clearance`; BGA pads get `pad_clearance` |
| no per-via / per-side tenting in KiCad 7 | explicit mask openings in a named board group, regenerated by `apply_routing` |
| DRC positions of some footprint graphics (silk polygons) are reported in footprint-local coordinates | only affects cosmetic warnings; item coordinates of copper violations are board coordinates |
| unrouted boards report the planes as `isolated_copper` warnings (nothing connects to them yet) | disappears once a via or pad reaches the plane |

## Limitations of the core

* Outline shapes: circle, rounded polygon, stadium slot, general closed
  line + arc path (`PathShape`, e.g. a circle clipped by chords).  Paths must
  not self-intersect (not checked).  Cutouts that cross the edge are resolved
  by a boolean operation and arcs are re-fitted (exact for circles known from
  the input shapes); free-form splines are not supported.
* `geometry.outline_polygon` approximates arcs to 5 um (inscribed outer
  boundary, circumscribed cutouts, i.e. always conservative).  Pad polygons
  come from KiCad and lie up to ~5 um INSIDE the true round copper; use
  `PlacedPad.inflated(distance)` (adds `geometry.PAD_POLYGON_TOLERANCE`) for
  conservative clearance shapes.
* Planes are simple filled zones (whole board or one shape), optional thermal
  reliefs; no hatched fills, no teardrops.
* Only through vias; blind/buried/micro vias are not modelled.  Via
  tenting is per board side, not per via; plugging is not modelled.
* Fine geometry is tied to net classes and pad overrides, not to board
  regions: a Fine-class net may use 0.09 mm tracks anywhere on the board.
* `Design.add_body_keepout` needs a pad-free centre (peripheral packages);
  it raises for BGAs and exposed-pad packages.
* Castellated *edge* pads of the board itself (`PadSpec(kind="castellated")`)
  are emitted with KiCad's castellated pad property and load in pcbnew, but no
  board with its own castellations has been taken through DRC.  Oblong (slot)
  drills are not supported in custom footprints.
* The checks are ERC-style, not a simulator: for example they cannot tell that
  a regulator's enable pin is driven to the wrong level.
* KiCad 7 only (file format 20221018).

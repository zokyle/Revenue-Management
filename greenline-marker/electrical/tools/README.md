# gleda - GreenLine scripted EDA toolchain

`gleda` turns a "netlist as code" design description (Python) into a verified
KiCad 7 board.  KiCad's own DRC is the judge; nothing is reported as passing
unless KiCad says so.

This file documents the **core** of the toolchain (design model, checks,
footprints, board builder, DRC runner), the **router** and the **demo build**.
The fabrication outputs and the schematic generator build on the API
described here and are documented in their own sections / module docstrings.

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
    router.py      autorouter (escape stage, negotiated routing, end game,
                   cleanup, exact audit, plane-fill prediction)
    raster.py      routing grid and exact obstacle rasterisation
    _astar.py      A* search kernel (numba-compiled when numba is installed)
    routeplot.py   quick matplotlib picture of a routed design (debug aid)
  demo/
    demo_design.py     the GreenLine DEMO board (stand-in for the real GL-1)
    build_demo.py      checks -> board -> route -> DRC -> outputs -> schematic
    demo_out/          everything the last demo build produced
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

* Units are millimetres.  The design origin is the **board centre** (for the
  D-shaped board: the centre of the circle), **+x is right, +y is up** as seen
  from the top of the board; rotation is counter-clockwise positive.
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
  `Design.add_placement_keepout(shape, side="top", name=...)` is the short
  form (no parts, copper unrestricted) - e.g. the 1.6 mm feet of the tub posts
  that land on the board.  Such an area may sit on an NPTH locating hole: the
  hole is a footprint to KiCad, so `board.py` cuts the hole's courtyard out of
  the rule area (a "keyhole" outline) and KiCad reports parts in the area but
  not the hole.

### Height-limited zones

`Design.add_height_limit(shape, max_height, side="top", exempt=("U2",),
name=...)` describes an enclosure feature that hangs over the board (the
camera hoods of the tub: nothing taller than 0.95 mm but the camera).  KiCad 7
has no height rule, so this is a check only: a part body inside the zone that
is taller is a `height_limit` error, a part without `height_mm` there a
`height_unknown` warning.  The zones are part of `Design.to_dict()` for the
mechanical team.

### Locating holes and slots

`Outline.add_hole(x, y, drill, name)` is a non-plated drilled hole (a
board-only footprint with an NPTH pad).  `Outline.add_npth_slot(x, y, width,
length, rotation=0)` is a non-plated slot given by its overall size, drawn as
a routed stadium on Edge.Cuts - copper keeps the copper-to-edge distance from
it and KiCad checks that.  The GL-1 locating features:

```python
outline = Outline(PathShape.d_shape(21.1, 17.3))
outline.add_hole(-4.2, 14.55, 1.15, name="H1")
outline.add_npth_slot(4.2, 14.55, width=1.15, length=1.65)
```

### Planes that share their layer with tracks

`design.add_plane("V2V8", "In2.Cu", routable=True)` makes In2.Cu the V2V8
plane AND keeps it a routing layer (`Design.signal_layers()` lists it).  The
router connects every V2V8 pad with a stub and a via (as for any plane),
routes on that layer only what does not fit elsewhere
(`RouterOptions.plane_layer_cost`) and, because tracks cut a plane, predicts
the fill (`router.plane_regions`) and gives every pad the fill does not reach
a real track.  KiCad's zone fill and DRC then confirm it.

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

## What a router can rely on (all verified against KiCad 7.0.11 DRC)

Inputs from the model:

```python
from gleda import geometry
pads = geometry.placed_pads(design)        # PlacedPad: ref, number, net, x, y, layers,
                                           # polygon (shapely, board mm), shape, w, h,
                                           # rotation, kind, drill, side, clearance
by_net = geometry.pads_by_net(design)      # net -> pads to connect
board_poly = geometry.outline_polygon(design.outline)   # conservative board area
holes = geometry.hole_polygons(design.outline)           # NPTH holes (also design.outline.holes)
for ko in design.keepouts:
    ko.layer_names(design.copper_layers), ko.tracks, ko.vias, geometry.keepout_polygon(ko)
design.signal_layers()                     # copper layers without a whole-board plane
design.plane_layers("GND")                 # layers where the net has a plane -> stub + via
design.track_width(net), design.min_track_width(net), design.via_size(net)
design.clearance(net_a, net_b, local_a=pad.clearance)    # what KiCad will require
r = design.rules                           # copper_to_edge, hole_clearance, hole_to_hole, ...
```

Rules of the judge:

* Track / via / pad clearance is `Design.clearance(...)`; distances between
  straight tracks and round or rectangular pads are evaluated exactly (a
  0.09 mm track exactly 0.09 mm from a round pad passes).
* Copper to board edge is measured to the centre line of the 0.05 mm
  Edge.Cuts graphics.  KiCad polygonises arcs (5 um per shape), so round copper
  next to a curved edge loses a few micrometres: generate with
  `geometry.DRC_SLACK` (0.01 mm) of extra distance.  `outline_polygon` is
  already conservative by `tol` (5 um).
* Pad polygons from KiCad lie up to ~5 um inside round copper; use the pad's
  `shape` / `w` / `h` for exact maths or `PlacedPad.inflated(distance)`.
* Through vias: 0.50 / 0.25 mm; hole to hole 0.25 mm also applies to vias of
  the SAME net; hole wall to foreign copper 0.20 mm; a via keep-out on any
  layer blocks through vias; a via inside a whole-board plane of another net
  is isolated by the zone fill, a via of the plane's net connects solidly.
* Tracks of different nets that touch get their nets silently merged by KiCad
  when the copper cluster has no pad: `board.apply_routing` detects this and
  raises (`strict=True`).
* Track width below `Design.min_track_width(net)` is a DRC error through the
  generated `.kicad_dru`.
* Zones are not filled by `build_board` / `apply_routing`; `drc.run_drc`
  refills and saves them before checking.

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

## Router (`gleda/router.py`)

```python
from gleda import router, board, drc

result = router.route(design)                      # or route(design, RouterOptions(...))
print(result.summary())                            # routed 261/261 connections (100.0 %) ...
result.complete                                    # every connection made, audit clean
result.unrouted                                    # [Unrouted(net, pieces)] - never hidden
board.apply_routing(files.pcb, result.tracks, result.vias, via_tenting=design.via_tenting)
drc.assert_clean(drc.run_drc(files.pcb))           # KiCad's zone fill + DRC is the judge

router.route_board(design, files.pcb)              # the same in one call -> (RouteResult, DrcResult)
router.save_routing("routing.json", design, result)        # deterministic file
router.load_routing("routing.json", design)                # fingerprint-checked, re-audited
```

### How it routes

1. **Grid and obstacle maps.**  Tracks run between the nodes of a 0.05 mm grid
   in 8 directions, vias sit on nodes.  For every track width / clearance and
   via size in use the router keeps maps of where the centre of such a track
   or via may not be: every pad on every layer, routed copper, keep-outs,
   board edge, cutouts and drilled holes, each grown by exactly the clearance
   KiCad will ask for (`Design.clearance`: the larger class clearance of the
   two nets or the pad's own override; hole-to-copper; hole-to-hole, also
   within one net; copper-to-edge plus `geometry.DRC_SLACK`).  Distances are
   exact (`gleda/raster.py`): a 0.09 mm track passes between two 0.23 mm balls
   at 0.5 mm pitch with exactly 0.09 mm on both sides.  Pads whose centre is
   not on the grid are entered at a node inside the pad and connected to the
   centre with a short stub.
2. **Units.**  A net is cut into connections (the edges of its minimum
   spanning tree); each connection joins the *copper* of its two sides
   wherever they are closest, so multi-pin nets become trees with T junctions.
   A pad of a plane net (whole-board plane on an inner layer) gets a stub and
   a through via instead - never a via in the pad, neighbours may share one.
3. **Stage A - array escape.**  The pads of each fine-pitch array (nine or
   more round pads at 0.65 mm pitch or less) and the other pads in a 3 mm
   window around it are routed first, among themselves: each signal pad out
   to the rim of the window (any layer, pulled toward the rest of its net) or
   to a pad of its net inside the window, each plane pad to its via, no via
   closer than 0.75 mm to the ball field.  This fan-out is negotiated to zero
   conflicts and frozen.
4. **Negotiation.**  Everything else is routed with other nets' copper allowed
   at a price (A*, integer costs, via cost, optional preferred direction per
   layer); the units in conflict are rerouted while the price of sharing and
   the history cost of contested cells rise.
5. **End game.**  Remaining conflicts are ripped up; from then on only clean
   copper is accepted.  An open connection may push others aside if they all
   find a clean path again (bounded cascade, undone otherwise); connections
   still open trigger another negotiation wave.  A class with
   `min_track_width` may neck a connection down as the last resort.
6. **Planes.**  `plane_regions()` predicts KiCad's zone fill.  A pad whose via
   lands in a piece of the plane that tracks or via clearances have cut off
   gets a real track to the main part.
7. **Improvement, cleanup, audit.**  Each connection is rerouted once along
   the plain shortest path (kept if shorter); collinear pieces are merged,
   stubs and loops removed, segments split at junctions.  `audit()` then
   re-checks all copper with exact geometry and derives the connectivity from
   the copper alone - that is where `RouteResult.unrouted` comes from.

### Per-net options (on `Design.net(...)` / `gleda.model.Net`)

| option | effect |
|--------|--------|
| `netclass="Fine"` | track width, clearance and via of the class; the clearance to another net is the larger of the two classes |
| `width=0.4` | this net's track width (never necked down) |
| `layers=("F.Cu",)` | routing layers the net may use |
| `max_vias=0` | upper limit of vias for the whole net |
| `no_route=True` | leave the net to you (not routed, not counted) |
| `priority=1` | routed before nets of lower priority |
| `NetClass.min_track_width` | nets of the class may neck down to this width (pads narrower than the track, last resort in the end game) |
| `Design.add_plane(net, layer)` | the net is not routed pad to pad: stub + via into the plane |
| `Design.add_plane(net, layer, routable=True)` | the same, and the layer stays a routing layer |

`RouterOptions` (all documented in the class docstring) tunes the router
itself: `grid`, `layers`, `via_cost`, `layer_directions` (`{"F.Cu": "h",
"B.Cu": "v"}`), `plane_layer_cost`, `array_via_keepout`, `escape_reach`,
`max_iterations`, `patience`, `waves`, `ripup_depth`, `improve_passes`,
`time_limit`, `progress` (a callable that receives log lines).

### Router: limits

* Through vias only, one via size per net class, vias on grid nodes.
* Tracks are 0 / 45 / 90 degree grid segments (plus short stubs to off-grid
  pad centres); no arcs, no teardrops, no length or skew matching, no
  differential pairs (USB D+/D- are routed as two ordinary nets).
* One width per connection: a class with `min_track_width` necks a whole
  connection (pad to junction) down, not just its last millimetre.
* Pads smaller than the grid pitch must sit on the grid (the 0.5 mm-pitch
  balls do); a pad that contains no grid node is entered at the nodes around
  its centre.
* Fine-pitch arrays are recognised by their round pads; the escape of a
  full-matrix array deeper than two rings on two routing layers is beyond
  this router.
* A net class's clearance applies along the whole net (KiCad's rule), so a
  fine-class net may run its fine track anywhere - give the fine class only
  to the nets that need it.
* The plane-fill prediction is deliberately a little pessimistic (0.02 mm);
  it may add a bridging track KiCad would not have needed.  Thermal reliefs
  are not modelled (planes connect solid).
* It is a negotiating maze router, not a shove router: on a board this dense
  the result is DRC-clean and complete but not pretty - expect more vias and
  longer tracks than a hand layout.  Analog and RF nets deserve manual
  routing (`no_route=True`).
* Run time grows with board area / grid pitch and with congestion; without
  numba the search kernel runs in pure Python (about 100x slower - fine for
  the unit tests, not for the demo board).
* Routing is reproducible but not stable: a small change of the design can
  change many tracks.

## Demo build (`demo/build_demo.py`)

`demo/demo_design.py` is a stand-in for the real GL-1 board with the same
mechanics: D-shaped outline (r = 21.1 mm, flat at y = 17.3 mm), 4 layers,
0.8 mm, NPTH locating hole and slot, eight post-foot placement keep-outs, a
height-limited zone under each camera hood, LQFP-64 MCU, two 25-ball 0.5 mm
BGAs sharing an 11-signal bus, LGA sensors, flash, regulators, 10-pin FPC,
61 x 0402, and on the bottom a 16-LED ring (charlieplexed on 5 lines), a
photodiode and seven bare contact pads.  GND is a solid plane on In1.Cu;
In2.Cu is the V2V8 plane and the third routing layer.

```
cd electrical/tools
/usr/bin/python3 demo/build_demo.py                   # all stages
/usr/bin/python3 demo/build_demo.py --reuse-routing   # skip the router when the design is unchanged
/usr/bin/python3 demo/build_demo.py --stages checks,board,route,drc
```

The script exits non-zero unless every stage passed: 0 check errors, 100 %
of the connections routed with a clean audit, KiCad DRC with 0 errors and 0
unconnected items (only the cosmetic silkscreen checks listed in
`drc.COSMETIC_CHECKS` are tolerated, and they are still reported), and the
later stages.  `demo_out/build_summary.json` records every stage,
`routing.json` the copper (identical on every run of the same design),
`routing_log.txt` the router's progress, `drc.json` / `drc_report.txt` what
KiCad said.

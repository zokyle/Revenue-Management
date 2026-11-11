"""gleda - GreenLine scripted EDA toolchain (netlist-as-code -> KiCad 7 board).

Modules
-------
model       design description (pure Python)
coords      the one place where design (+y up) <-> KiCad (+y down) conversion lives
geometry    shapely helpers: outline polygons, placed pads, courtyards
footprints  programmatic footprints + KiCad library wrappers
checks      ERC-style and placement checks
board       .kicad_pcb / .kicad_pro generation, routing primitives in/out (pcbnew)
drc         zone fill + KiCad DRC runner and report parser
kicad_cli   thin kicad-cli wrappers (SVG export, SVG reader for orientation checks)
router      autorouter: array escape, negotiated routing, end game, cleanup, audit
raster      routing grid and exact obstacle rasterisation (used by the router)
routeplot   quick matplotlib picture of a routed design (debugging aid)
outputs     Gerbers, drill, pick-and-place, BOM, netlist / mechanical JSON, STEP,
            renders, fab README and zip - each checked against the design model
schematic   KiCad 7 schematic generator, PDF export, netlist round trip
"""
from .model import (  # noqa: F401
    Design, Part, Pin, Net, NetClass, Rules, US_4L_STD, US_4L_FINE, Outline, Circle,
    RoundedPolygon, Slot, PathShape, Hole, Keepout, HeightLimit, Plane, FineArea, Stackup,
    Track, Via, two_pin, n_pin, TOP, BOTTOM, ALL_LAYERS, VIA_TENTING,
)

__version__ = "0.4.0"

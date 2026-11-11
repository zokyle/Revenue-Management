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
"""
from .model import (  # noqa: F401
    Design, Part, Pin, Net, NetClass, Rules, US_4L_STD, Outline, Circle,
    RoundedPolygon, Slot, Hole, Keepout, Plane, Stackup, Track, Via,
    two_pin, n_pin, TOP, BOTTOM, ALL_LAYERS,
)

__version__ = "0.1.0"

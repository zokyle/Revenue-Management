"""Silkscreen text for a gleda board file.

gleda 0.4.0 has no board-level text: a design can show reference designators
on the silkscreen (``Design.silk_refs``) and footprints can carry lines and
polygons, nothing else.  A legend (pin order of a contact row, board name) is
therefore added to the ``.kicad_pcb`` here, with pcbnew, AFTER
``gleda.board.build_board`` and BEFORE the routing is applied and KiCad's DRC
runs - so the text is on the board KiCad judges and in the Gerbers the
toolchain plots from that board.  Reported as a toolchain limitation.

    add_silk_text(pcb_path, [SilkText("1 VBUS", -7.62, 4.9, rotation=90.0, side="top"), ...])

Coordinates are design mm (board centre origin, +y up, seen from the top) on
both sides, like part positions; text on the bottom side is mirrored so that
it reads correctly from below.  Existing legend texts (the group
``gl1_silk_legend``) are replaced, so the call is idempotent.
"""
import os
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from gleda import board as _board, coords                                # noqa: E402

GROUP = "gl1_silk_legend"


@dataclass(frozen=True)
class SilkText:
    text: str
    x: float
    y: float
    rotation: float = 0.0            # degrees, counter-clockwise seen from the top
    side: str = "top"                # "top" | "bottom"
    height: float = 0.8              # mm (the rule set's minimum text height is 0.5)
    thickness: float = 0.12
    justify: str = "center"          # "left" | "center" | "right" (horizontal, along the text)


def add_silk_text(pcb_path, items):
    """Write ``items`` to F.SilkS / B.SilkS of the board file; returns the number written."""
    import pcbnew
    brd = pcbnew.LoadBoard(pcb_path)
    for group in list(brd.Groups()):
        if str(group.GetName()) == GROUP:
            for it in list(group.GetItems()):
                brd.Remove(it)
            brd.Remove(group)
    group = pcbnew.PCB_GROUP(brd)
    group.SetName(GROUP)
    brd.Add(group)
    pcbnew.KIID.SeedGenerator(0x51CC)                    # the same identifiers on every run
    just = {"left": pcbnew.GR_TEXT_H_ALIGN_LEFT, "center": pcbnew.GR_TEXT_H_ALIGN_CENTER,
            "right": pcbnew.GR_TEXT_H_ALIGN_RIGHT}
    for it in items:
        t = pcbnew.PCB_TEXT(brd)
        t.SetText(it.text)
        bottom = it.side == "bottom"
        t.SetLayer(pcbnew.B_SilkS if bottom else pcbnew.F_SilkS)
        kx, ky = coords.to_kicad_nm(it.x, it.y)
        t.SetPosition(pcbnew.VECTOR2I(kx, ky))
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(it.height), pcbnew.FromMM(it.height)))
        t.SetTextThickness(pcbnew.FromMM(it.thickness))
        t.SetTextAngle(pcbnew.EDA_ANGLE(it.rotation, pcbnew.DEGREES_T))
        t.SetHorizJustify(just[it.justify])
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetMirrored(bottom)
        brd.Add(t)
        group.AddItem(t)
    _board.save_board(brd, pcb_path)
    return len(items)

# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Frozen claude_code open-vocab discovery for the dreamlab capture.

This is the real output of a *vision* overseer pass (the claude_code agent,
2026-06-25) over 8 representative frames spread across the 1656-frame dreamlab
sequence (frames 00001, 00240, 00480, 00720, 00960, 01200, 01440, 01656 under
``output/dreamlab/locked/images/``). Because DiffusionGemma is text-only, the
agent itself acted as the vision overseer (see object_discovery.py).

These records are what should REPLACE the static ``sam3_concepts`` for dreamlab.
Confidence reflects how reliably the object was distinguishable across frames.
"""

from __future__ import annotations

# Frame filenames the agent actually read.
DREAMLAB_FRAMES = [
    "frame_00001.png", "frame_00240.png", "frame_00480.png", "frame_00720.png",
    "frame_00960.png", "frame_01200.png", "frame_01440.png", "frame_01656.png",
]

#: Open-vocabulary objects enumerated by the claude_code vision overseer.
DREAMLAB_DISCOVERIES = [
    {
        "label": "workbench",
        "aliases": ["plywood workbench", "built-in bench", "yellow-top bench"],
        "confidence": 0.97,
        "description": "Large built-in plywood workbench with a yellow laminate "
                       "top and a rolling caster storage cube underneath; a "
                       "second plywood bench carcass with arched hand-holds is "
                       "under construction.",
        "source_frames": ["frame_00960.png", "frame_01200.png", "frame_01656.png"],
    },
    {
        "label": "step ladder",
        "aliases": ["ladder", "aluminium step ladder", "folding ladder"],
        "confidence": 0.95,
        "description": "Yellow/silver folding aluminium step ladder, leaned and "
                       "folded against the wall in several frames.",
        "source_frames": ["frame_00480.png", "frame_01440.png", "frame_01656.png"],
    },
    {
        "label": "wet and dry vacuum",
        "aliases": ["vacuum cleaner", "Henry vacuum", "Numatic vacuum",
                    "Karcher wet/dry vacuum", "shop vac"],
        "confidence": 0.94,
        "description": "Cylinder wet/dry shop vacuum(s): a red/black Numatic-Henry "
                       "style canister and a yellow/grey Karcher-style unit, with "
                       "coiled hoses on the floor.",
        "source_frames": ["frame_00001.png", "frame_00720.png", "frame_01440.png"],
    },
    {
        "label": "cordless stick vacuum",
        "aliases": ["stick vacuum", "Shark vacuum", "handheld vacuum"],
        "confidence": 0.9,
        "description": "Pink/magenta cordless upright stick vacuum (Shark-style) "
                       "standing on the laminate floor by the doorway.",
        "source_frames": ["frame_00001.png"],
    },
    {
        "label": "stackable tool boxes",
        "aliases": ["toolbox", "tool box tower", "TSTAK boxes",
                    "Stanley FatMax stack", "tool chest"],
        "confidence": 0.93,
        "description": "Tower of black-and-yellow stackable tool boxes (Stanley "
                       "TSTAK / FatMax style) plus loose hard tool cases stacked "
                       "against the wall.",
        "source_frames": ["frame_01200.png", "frame_01656.png", "frame_01440.png"],
    },
    {
        "label": "hard tool case",
        "aliases": ["tool case", "power tool case", "Makita case",
                    "black tool case"],
        "confidence": 0.88,
        "description": "Large black hard-shell plastic tool/power-tool carry "
                       "cases (one Makita-blue) sitting on the floor.",
        "source_frames": ["frame_00480.png", "frame_01200.png", "frame_01656.png"],
    },
    {
        "label": "mitre saw",
        "aliases": ["mitre saw", "chop saw", "circular saw", "DeWalt saw"],
        "confidence": 0.8,
        "description": "Power saw with a yellow (DeWalt-style) blade guard plus a "
                       "track/guide-rail circular saw seen on the floor and the "
                       "saw bench.",
        "source_frames": ["frame_00480.png", "frame_00720.png", "frame_01440.png"],
    },
    {
        "label": "dartboard",
        "aliases": ["dart board"],
        "confidence": 0.92,
        "description": "Bristle dartboard mounted on the far wall, beside an oval "
                       "green-baize games/poker table.",
        "source_frames": ["frame_00001.png", "frame_01440.png"],
    },
    {
        "label": "poker table",
        "aliases": ["games table", "green baize table", "card table"],
        "confidence": 0.78,
        "description": "Oval green-baize poker/games table leaned against the "
                       "wall, partly wrapped in protective plastic.",
        "source_frames": ["frame_00001.png", "frame_01440.png"],
    },
    {
        "label": "dining chair",
        "aliases": ["chair", "kitchen chair", "wooden chair"],
        "confidence": 0.86,
        "description": "Wooden dining/kitchen chair with a dark (black) seat pad, "
                       "standing on the floor in the wide room shots.",
        "source_frames": ["frame_01440.png"],
    },
    {
        "label": "trestle stand",
        "aliases": ["sawhorse", "trestle", "saw stand", "trestle table"],
        "confidence": 0.82,
        "description": "Black metal folding trestle/sawhorse stands used to "
                       "support work; blue trestles also visible against the wall.",
        "source_frames": ["frame_01440.png", "frame_01656.png"],
    },
    {
        "label": "desk fan",
        "aliases": ["cooling fan", "pedestal fan", "fan"],
        "confidence": 0.72,
        "description": "Small white desk/cooling fan sitting on top of the tool "
                       "box tower.",
        "source_frames": ["frame_01200.png"],
    },
    {
        "label": "plastic storage tote",
        "aliases": ["storage box", "clear tote", "Really Useful Box"],
        "confidence": 0.8,
        "description": "Clear plastic lidded storage totes/boxes on the floor "
                       "holding screws and small parts.",
        "source_frames": ["frame_00720.png", "frame_01656.png"],
    },
    {
        "label": "spirit level",
        "aliases": ["bubble level", "level", "yellow level"],
        "confidence": 0.7,
        "description": "Long yellow aluminium spirit (bubble) level lying on the "
                       "workbench top.",
        "source_frames": ["frame_00960.png"],
    },
    {
        "label": "paint tins",
        "aliases": ["paint cans", "paint pots", "tins"],
        "confidence": 0.68,
        "description": "Round metal paint/varnish tins and pots scattered on the "
                       "floor and bench.",
        "source_frames": ["frame_00240.png", "frame_00480.png"],
    },
    {
        "label": "laminate flooring planks",
        "aliases": ["floor planks", "laminate planks", "wood flooring",
                    "engineered boards"],
        "confidence": 0.9,
        "description": "Stacks and scattered runs of wood-effect laminate/"
                       "engineered floor planks being laid throughout the room "
                       "(this is a flooring-install scene).",
        "source_frames": ["frame_00001.png", "frame_00480.png", "frame_00720.png"],
    },
    {
        "label": "interior door",
        "aliases": ["wooden door", "door slab", "oak door"],
        "confidence": 0.85,
        "description": "Oak-veneer interior door slabs — one hung in the frame, "
                       "others stacked/leaning against the wall with their trim.",
        "source_frames": ["frame_00001.png", "frame_00480.png", "frame_01440.png"],
    },
]

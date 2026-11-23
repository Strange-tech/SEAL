#!/usr/bin/env python3
"""Generate the 10 assets, each constrained by its own --box, then set up the viewer.

This is the "with box" version of ``10_assets_only_text.sh``: the same ten object
descriptions, but every generation is given a ``--box`` target via ``main.py``
(the box is a soft size/placement reference — see ``main.py --box``). After the
ten generations finish, the script writes:

  * ``<out>/<name>.json``   — emitted per asset (asset_dir + center + dims + rpy),
    written by ``main.py --emit-result``;
  * ``<out>/_boxes.json``   — the ten constraint boxes as a layout JSON (for viewer);
  * ``<out>/scene.json``    — viewer config ``{layout, arti:[...]}``.

Run from the ArtiAgent root:

    python test/10_assets_with_box.py [--dry-run] [--view] [--port 8770]

``--dry-run`` only prints the ten ``main.py`` commands without calling the LLM.
The boxes are laid out in a 5 x 2 grid so the ten objects do not overlap in the
viewer; box dims are sensible targets for each object (you can edit ``ITEMS``).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ARTI = Path(__file__).resolve().parent.parent          # ArtiAgent root
OUT_DIR = ARTI / "assets" / "10_assets_with_box"

# --------------------------------------------------------------------------- #
# single source of truth: (name, task, center [x,y,z], dims [w,h,d])
# center.y is box height/2 so every box is floor-aligned; grid: 5 cols x 2 rows.
# --------------------------------------------------------------------------- #
COLS = [-2.4, -1.2, 0.0, 1.2, 2.4]
ROWS = [0.0, 2.5]

_RAW = [
    ("a_wooden_chair",       "a wooden chair",       [0.5, 1.0, 0.55]),
    ("a_round_coffee_table", "a round coffee table", [0.8, 0.5, 0.8]),
    ("a_floor_lamp",         "a floor lamp",         [0.45, 1.8, 0.45]),
    ("a_desk_lamp",          "a desk lamp",          [0.3, 0.6, 0.3]),
    ("a_ceramic_mug",        "a ceramic mug",        [0.12, 0.1, 0.1]),
    ("a_glass_bottle",       "a glass bottle",       [0.1, 0.25, 0.1]),
    ("a_hardcover_book",     "a hardcover book",     [0.18, 0.26, 0.04]),
    ("a_chest_of_drawers",   "a chest of drawers",   [1.0, 1.2, 0.6]),
    ("a_flower_vase",        "a flower vase",        [0.15, 0.3, 0.15]),
    ("a_wall_clock",         "a wall clock",         [0.3, 0.3, 0.05]),
]

ITEMS = []
for i, (name, task, dims) in enumerate(_RAW):
    w, h, d = dims
    cx = COLS[i % len(COLS)]
    cz = ROWS[i // len(COLS)]
    cy = h / 2.0
    ITEMS.append({"name": name, "task": task, "center": [cx, cy, cz], "dims": dims})


def box_arg(item):
    c, d = item["center"], item["dims"]
    return "%g,%g,%g, %g,%g,%g" % (c[0], c[1], c[2], d[0], d[1], d[2])


def main():
    ap = argparse.ArgumentParser(description="Generate 10 assets, each with a --box, and set up the viewer.")
    ap.add_argument("--provider", default="deepseek")
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--dry-run", action="store_true", help="print the main.py commands without running them")
    ap.add_argument("--view", action="store_true", help="launch viewer.py after generation")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- generate ----
    for item in ITEMS:
        emit = out_dir / (item["name"] + ".json")
        cmd = [sys.executable, "main.py",
               "--provider", args.provider, "--model", args.model,
               "--task", item["task"],
               "--box", box_arg(item),
               "--emit-result", str(emit)]
        print(" ".join(cmd))
        if not args.dry_run:
            subprocess.run(cmd, cwd=str(ARTI), check=True)

    if args.dry_run:
        print("\n(dry-run: skipped generation)")
        return 0

    # ---- boxes layout JSON (viewer layout format: C/D/theta, theta in degrees) ----
    nodes = []
    for i, item in enumerate(ITEMS):
        nodes.append({
            "id": "box%d" % i,
            "type": "box",
            "C": [round(v, 4) for v in item["center"]],
            "D": [round(v, 4) for v in item["dims"]],
            "theta": [0.0, 0.0, 0.0],
        })
    (out_dir / "_boxes.json").write_text(
        json.dumps({"nodes": nodes, "edges": []}, indent=2) + "\n", encoding="utf-8")

    scene = {"layout": "_boxes.json",
             "arti": sorted(item["name"] + ".json" for item in ITEMS)}
    (out_dir / "scene.json").write_text(
        json.dumps(scene, indent=2) + "\n", encoding="utf-8")

    print("\nwrote _boxes.json + scene.json + %d asset results under %s" % (len(ITEMS), out_dir))

    if args.view:
        cmd = [sys.executable, str(ARTI / "viewer.py"), "--config",
               str(out_dir / "scene.json"), "--host", args.host, "--port", str(args.port)]
        print("launching viewer: %s" % " ".join(cmd))
        subprocess.run(cmd)
    else:
        print("to view: python viewer.py --config %s --host %s --port %s"
              % (out_dir / "scene.json", args.host, args.port))
    return 0


if __name__ == "__main__":
    sys.exit(main())

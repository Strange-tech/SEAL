#!/usr/bin/env python3
"""Smoke-test ArtiAgent ``--box`` + ``--image`` against a LayoutAgent scene.

For each ``type: object`` node in a LayoutAgent scene graph, this derives:

  * ``--image``  the object cropped out of the perception image via its SAM mask
                 (object kept, background zeroed), saved under ``test/masks/``.
  * ``--box``    ``'<cx,cy,cz>,<w,h,l>'`` from the node ``C`` / ``D`` (y-up, +z-forward).

and then runs::

    python main.py --task "Generate a 3D articulated model of <desc>" \
                   --image <crop.png> --box '<cx,cy,cz>,<w,h,l>' \
                   --emit-result <result.json>

The node-id -> SAM-mask-name link is scene-specific (LayoutAgent invents snake_case
ids independently of the SAM prompt strings), so it is declared in OBJECT_MASK_MAP.

Examples:
    python test/test_box.py --object scale              # run one object
    python test/test_box.py --object scale --dry-run    # print the command only
    python test/test_box.py --scene kitchen --all       # run every mapped object
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as e:
    sys.exit(f"missing dependency: {e}\nrun inside the `layout` conda env (numpy + Pillow)")

ARTI_DIR = Path(__file__).resolve().parents[1]          # ArtiAgent/
LAYOUT_OUT = ARTI_DIR.parent / "BaseAgent" / "output" / "layoutagent"

# node_id -> SAM mask name (keys of the perception-state manifest.json "masks")
OBJECT_MASK_MAP = {
    "kitchen": {
        "countertop": "countertop",
        "pour_over": "coffee carafe with dripper",
        "coffee_scale": "coffee scale",
        "wooden_board": "wooden stand_1",
        "bean_jar": "jar of coffee beans_2",
        "coffee_grinder": "coffee grinder_3",
        "mug": "cup_0",
        "cloth": "cloth",
        "wooden_stand": "wooden stand_0",
        "plant_left": "plant pot_2",
        "plant_right": "plant pot_1",
    },
}

# scene -> (scene-graph JSON filename, perception-state dir name), relative to LAYOUT_OUT
SCENE_DEFAULTS = {
    "kitchen": {
        "layout": "generate-the-layout-v2.json",
        "state": "kitchen_v2",
    },
}


def resolve_scene(scene, layout, state):
    if layout and state:
        return Path(layout), Path(state)
    d = SCENE_DEFAULTS.get(scene)
    if d is None:
        sys.exit(f"no defaults for scene {scene!r}; pass --layout and --state explicitly")
    return LAYOUT_OUT / d["layout"], LAYOUT_OUT / d["state"]


def load_scene(layout_path):
    data = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    return data.get("nodes", [])


def load_state(state_dir):
    manifest = json.loads((Path(state_dir) / "manifest.json").read_text(encoding="utf-8"))
    img = np.array(Image.open(Path(state_dir) / manifest["image"]).convert("RGB"))
    boxes = json.loads((Path(state_dir) / manifest["boxes"]).read_text(encoding="utf-8"))
    return img, boxes, manifest.get("masks", {})


def crop_masked(img, mask_path, box, out_path, pad=12):
    mask = np.load(mask_path)
    h, w = mask.shape
    x1, y1, x2, y2 = [float(v) for v in box]
    x1 = max(0, int(x1) - pad)
    y1 = max(0, int(y1) - pad)
    x2 = min(w, int(x2 + 0.999) + pad)
    y2 = min(h, int(y2 + 0.999) + pad)
    crop = img[y1:y2, x1:x2].copy()
    cmask = mask[y1:y2, x1:x2]
    crop[~cmask] = 0
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(crop).save(out_path)
    return out_path


def box_str(node):
    cx, cy, cz = node["C"]
    dx, dy, dz = node["D"]
    return ",".join(str(v) for v in (cx, cy, cz, dx, dy, dz))


def main():
    ap = argparse.ArgumentParser(description="Test ArtiAgent --box/--image from a LayoutAgent scene")
    ap.add_argument("--scene", default="kitchen", help="scene key in SCENE_DEFAULTS (default: kitchen)")
    ap.add_argument("--layout", help="explicit scene-graph JSON path (overrides scene default)")
    ap.add_argument("--state", help="explicit perception-state dir path (overrides scene default)")
    ap.add_argument("--object", help="node id to run (e.g. scale, carafe)")
    ap.add_argument("--all", action="store_true", help="run every mapped object node")
    ap.add_argument("--dry-run", action="store_true", help="print commands without running")
    ap.add_argument("--force", action="store_true", help="re-run objects whose result JSON already exists")
    ap.add_argument("--task", default=None, help="override the generated --task text")
    args = ap.parse_args()

    layout_path, state_dir = resolve_scene(args.scene, args.layout, args.state)
    if not Path(layout_path).is_file():
        sys.exit(f"layout JSON not found: {layout_path}")
    if not Path(state_dir).is_dir():
        sys.exit(f"state dir not found: {state_dir}")

    nodes = load_scene(layout_path)
    img, boxes, masks = load_state(state_dir)

    mask_map = OBJECT_MASK_MAP.get(args.scene, {})
    objects = [n for n in nodes if n.get("type") == "object"]

    if args.object:
        objects = [n for n in objects if n["id"] == args.object]
        if not objects:
            sys.exit(f"no object node with id {args.object!r}")
    elif not args.all:
        ids = [n["id"] for n in objects]
        print("available object nodes:")
        for i in ids:
            print(f"  {i}")
        print("\npass --object <id> to run one, or --all to run everything.")
        return

    for n in objects:
        node_id = n["id"]
        emit_path = (ARTI_DIR / "test" / "results" / f"{args.scene}__{node_id}.json").resolve()
        if emit_path.is_file() and not args.force:
            print(f"[skip] {node_id}: result already exists ({emit_path.name})")
            continue
        mask_name = mask_map.get(node_id)
        if mask_name is None:
            print(f"[skip] {node_id}: no mask mapping for scene {args.scene!r}", file=sys.stderr)
            continue
        if mask_name not in masks:
            print(f"[skip] {node_id}: mask {mask_name!r} not in manifest", file=sys.stderr)
            continue
        if mask_name not in boxes:
            print(f"[skip] {node_id}: no 2D box for mask {mask_name!r}", file=sys.stderr)
            continue

        crop_path = (ARTI_DIR / "test" / "masks" / f"{args.scene}__{node_id}.png").resolve()
        crop_masked(img, Path(state_dir) / masks[mask_name], boxes[mask_name], crop_path)

        desc = re.sub(r"_\d+$", "", mask_name).replace("_", " ")
        task = args.task or f"Generate a 3D articulated model of a {desc}"
        bstr = box_str(n)

        cmd = [
            sys.executable, "main.py",
            "--task", task,
            "--image", str(crop_path),
            "--box", bstr,
            "--structure", "always",
            "--emit-result", str(emit_path),
        ]
        print(f"==== {node_id} ====")
        print(f"  image: {crop_path}")
        print(f"  box:   {bstr}")
        print(f"  task:  {task}")
        if args.dry_run:
            print(f"  would run: {' '.join(cmd)}")
            continue
        print(f"  run:   {' '.join(cmd)}")
        r = subprocess.run(cmd, cwd=str(ARTI_DIR))
        if r.returncode != 0:
            print(f"[FAIL] {node_id} exited {r.returncode}", file=sys.stderr)


if __name__ == "__main__":
    main()

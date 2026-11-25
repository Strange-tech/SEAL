#!/usr/bin/env python3
"""Standalone swept-bbox inspection + viewer scene.

Compute the joint-range (swept) AABB and the zero-pose (rest) AABB of ArtiAgent
models — either for a single model.py (standalone test) or for every asset result
JSON under an asset dir — then optionally write + launch a viewer scene that
renders those boxes around the assets.

Run with the layout conda env (needs cadquery / manifold3d):

    ~/miniconda3/envs/layout/bin/python test/swept_bbox.py --model <path-to-model.py>
    ~/miniconda3/envs/layout/bin/python test/swept_bbox.py --asset-dir assets/10_assets_with_box --view --port 8770
"""
import argparse
import json
import sys
from pathlib import Path

ARTI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ARTI))

from agent.bbox import compute_model_swept_bbox, compute_rest_bbox  # noqa: E402


def resolve_model_py(asset_dir):
    ad = Path(asset_dir)
    rj = ad / "record.json"
    if rj.is_file():
        try:
            data = json.loads(rj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        mp = (data.get("artifacts") or {}).get("model_py")
        if mp:
            cand = ad / mp
            if cand.is_file():
                return cand
    for mp in ad.rglob("model.py"):
        return mp
    return None


def _vec(v):
    return ", ".join("%.4f" % x for x in v)


def main():
    ap = argparse.ArgumentParser(description="Inspect ArtiAgent swept (joint-range) bounding boxes.")
    ap.add_argument("--model", help="single model.py to inspect (standalone)")
    ap.add_argument("--asset-dir", help="batch: dir of asset result JSONs")
    ap.add_argument("--out-dir", default=str(ARTI / "assets" / "swept_bbox"))
    ap.add_argument("--view", action="store_true", help="launch viewer after writing the scene")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()

    # ---- standalone: single model.py ----
    if args.model:
        mp = Path(args.model).resolve()
        swept = compute_model_swept_bbox(mp, asset_root=ARTI / ".bbox_tmp")
        rest = compute_rest_bbox(mp, asset_root=ARTI / ".bbox_tmp")
        print("model:", mp)
        print("  swept bbox:      center=[%s] dims=[%s]" % (_vec(swept[0]), _vec(swept[1])))
        print("  rest  (zero-pose) bbox: center=[%s] dims=[%s]" % (_vec(rest[0]), _vec(rest[1])))
        return 0

    # ---- batch: one box pair per asset result JSON ----
    asset_dir = Path(args.asset_dir)
    if not asset_dir.is_dir():
        print("no such asset-dir: %s" % asset_dir, file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    jsons = sorted(p for p in asset_dir.glob("*.json")
                   if not p.name.startswith("_") and p.name != "scene.json")

    nodes = []
    arti = []
    for j in jsons:
        data = json.loads(j.read_text(encoding="utf-8"))
        ad = data.get("asset_dir")
        placement = data.get("center") or [0.0, 0.0, 0.0]
        name = j.stem
        mp = resolve_model_py(ad)
        if mp is None:
            print("!! %-24s no model.py under %s" % (name, ad), file=sys.stderr)
            continue
        swept = compute_model_swept_bbox(mp, asset_root=ARTI / ".bbox_tmp")
        rest = compute_rest_bbox(mp, asset_root=ARTI / ".bbox_tmp")
        sc, sd = swept
        rc, rd = rest
        # object is authored at origin and placed at `placement` (rpy==0 here)
        ws = [placement[i] + sc[i] for i in range(3)]
        wr = [placement[i] + rc[i] for i in range(3)]
        nodes.append({"id": "swept_" + name, "type": "swept_bbox",
                      "C": [round(v, 4) for v in ws], "D": [round(v, 4) for v in sd],
                      "theta": [0.0, 0.0, 0.0]})
        nodes.append({"id": "rest_" + name, "type": "rest_bbox",
                      "C": [round(v, 4) for v in wr], "D": [round(v, 4) for v in rd],
                      "theta": [0.0, 0.0, 0.0]})
        arti.append(str(j.resolve()))
        print("%-24s swept dims=[%s]  rest dims=[%s]" % (name, _vec(sd), _vec(rd)))

    # include the constraint boxes (--box targets) for comparison if present
    boxes_file = asset_dir / "_boxes.json"
    if boxes_file.is_file():
        try:
            cb = json.loads(boxes_file.read_text(encoding="utf-8"))
            nodes += cb.get("nodes", [])
        except (OSError, ValueError):
            pass

    layout_path = out_dir / "_swept_boxes.json"
    layout_path.write_text(json.dumps({"nodes": nodes, "edges": []}, indent=2) + "\n", encoding="utf-8")
    scene = {"layout": str(layout_path.resolve()), "arti": sorted(arti)}
    scene_path = out_dir / "scene.json"
    scene_path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    print("wrote %d box nodes -> %s" % (len(nodes), layout_path))
    print("wrote scene -> %s" % scene_path)

    if args.view:
        import subprocess
        cmd = [sys.executable, str(ARTI / "viewer.py"), "--config", str(scene_path),
               "--host", args.host, "--port", str(args.port)]
        print("launching: %s" % " ".join(cmd))
        subprocess.run(cmd)
    else:
        print("to view: python3 viewer.py --config %s --host %s --port %s"
              % (scene_path, args.host, args.port))
    return 0


if __name__ == "__main__":
    sys.exit(main())

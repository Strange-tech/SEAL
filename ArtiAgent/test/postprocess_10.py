#!/usr/bin/env python3
"""Post-process the 10 generated assets.

For each of the 10 most-recent records under data/records/:
  1. copy the materialized model.urdf + meshes into assets/10_assets_only_text/<name>/;
  2. compute the zero-pose world AABB (center + dims) by parsing the URDF and
     accumulating visual origins + joint translations;
  3. report whether the geometric center sits at the world origin.

The check assumes upright objects (rpy = 0 on the origins), which matches the
current authoring convention; rotation is therefore treated as translation-only.

Results are written to test/results_10_assets_only_text.txt.
"""
import glob
import json
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET

ARTI = Path("/mnt/sda/johnli/SEAL/ArtiAgent")
RECORDS = ARTI / "data" / "records"
MAT = ARTI / "data" / "cache" / "record_materialization"
OUT_ASSETS = ARTI / "assets" / "10_assets_only_text"
OUT_RESULTS = ARTI / "test" / "results_10_assets_only_text.txt"
CENTER_TOL = 0.05  # metres


def _vec(s):
    return [float(x) for x in s.split()]


def parse_urdf(urdf_path):
    tree = ET.parse(urdf_path)
    robot = tree.getroot()
    links = {}
    for link in robot.findall("link"):
        name = link.get("name")
        visuals = []
        for v in link.findall("visual"):
            geom = v.find("geometry")
            if geom is None:
                continue
            mesh = geom.find("mesh")
            if mesh is None or not mesh.get("filename"):
                continue
            origin = v.find("origin")
            xyz = _vec(origin.get("xyz")) if origin is not None else [0.0, 0.0, 0.0]
            visuals.append((mesh.get("filename"), xyz))
        links[name] = visuals
    joints = []
    for j in robot.findall("joint"):
        origin = j.find("origin")
        xyz = _vec(origin.get("xyz")) if origin is not None else [0.0, 0.0, 0.0]
        parent = j.find("parent").get("link")
        child = j.find("child").get("link")
        joints.append((parent, child, xyz))
    children = {c for (_, c, _) in joints}
    roots = [n for n in links if n not in children]
    return links, joints, roots


def link_offsets(links, joints, roots):
    """Zero-pose world translation for every link (translation-only)."""
    off = {r: (0.0, 0.0, 0.0) for r in roots}
    changed = True
    while changed:
        changed = False
        for parent, child, xyz in joints:
            if parent in off and child not in off:
                px, py, pz = off[parent]
                off[child] = (px + xyz[0], py + xyz[1], pz + xyz[2])
                changed = True
    return off


def compute_aabb(mat_dir):
    urdf = mat_dir / "model.urdf"
    if not urdf.is_file():
        return None
    links, joints, roots = parse_urdf(urdf)
    off = link_offsets(links, joints, roots)
    lo = [None, None, None]
    hi = [None, None, None]
    for name, visuals in links.items():
        if name not in off:
            continue
        lx, ly, lz = off[name]
        for mesh_rel, vxyz in visuals:
            mesh_file = mat_dir / mesh_rel
            try:
                with open(mesh_file, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if not line.startswith("v "):
                            continue
                        p = line.split()
                        x = float(p[1]) + vxyz[0] + lx
                        y = float(p[2]) + vxyz[1] + ly
                        z = float(p[3]) + vxyz[2] + lz
                        for i, c in enumerate((x, y, z)):
                            if lo[i] is None or c < lo[i]:
                                lo[i] = c
                            if hi[i] is None or c > hi[i]:
                                hi[i] = c
            except OSError:
                continue
    if lo[0] is None:
        return None
    center = [(lo[i] + hi[i]) / 2 for i in range(3)]
    dims = [hi[i] - lo[i] for i in range(3)]
    return center, dims


def slugify(title):
    out = []
    for ch in title.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("_")
    return "".join(out).strip("_") or "asset"


def main():
    OUT_ASSETS.mkdir(parents=True, exist_ok=True)
    records = sorted(RECORDS.glob("rec_*"), key=lambda p: p.stat().st_mtime)
    if not records:
        print("no records found")
        return
    records = records[-10:]

    lines = ["local coordinate system check", "=" * 60, ""]
    for rec in records:
        rid = rec.name
        title = "unknown"
        rj = rec / "record.json"
        if rj.is_file():
            data = json.loads(rj.read_text(encoding="utf-8"))
            title = (data.get("display") or {}).get("title") or "unknown"

        mat_dir = MAT / rid
        dst = OUT_ASSETS / slugify(title)
        if not mat_dir.is_dir():
            lines.append("[%s] no materialization dir %s" % (title, mat_dir))
            lines.append("")
            continue

        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(mat_dir, dst)

        result = compute_aabb(mat_dir)
        if result is None:
            lines.append("%s (%s): AABB unavailable" % (title, rid))
        else:
            center, dims = result
            off = max(abs(c) for c in center) > CENTER_TOL
            flag = "offset from origin" if off else "centered at origin"
            lines.append("%s (%s)" % (title, rid))
            lines.append("  center = [%.4f, %.4f, %.4f]  -> %s" % (center[0], center[1], center[2], flag))
            lines.append("  dims   = w %.3f  h %.3f  d %.3f  (x, y, z)" % (dims[0], dims[1], dims[2]))
        lines.append("")

    OUT_RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

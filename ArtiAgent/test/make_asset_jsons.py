#!/usr/bin/env python3
"""Create one result JSON per saved asset under assets/10_assets_only_text/.

Each JSON is {asset_dir, center, dims, rpy} so viewer.py can load it directly.
The AABB handles both <mesh> and <box>/<cylinder>/<sphere> primitives (translation-only).
"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ARTI = Path("/mnt/sda/johnli/SEAL/ArtiAgent")
ASSET_ROOT = ARTI / "assets" / "10_assets_only_text"


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
            origin = v.find("origin")
            xyz = _vec(origin.get("xyz")) if origin is not None else [0.0, 0.0, 0.0]
            # mesh
            mesh = geom.find("mesh")
            if mesh is not None and mesh.get("filename"):
                visuals.append(("mesh", mesh.get("filename"), xyz))
                continue
            box = geom.find("box")
            if box is not None and box.get("size"):
                visuals.append(("box", _vec(box.get("size")), xyz))
                continue
            cyl = geom.find("cylinder")
            if cyl is not None:
                r = float(cyl.get("radius", 0.5))
                l = float(cyl.get("length", 1.0))
                visuals.append(("cylinder", (r, l), xyz))
                continue
            sph = geom.find("sphere")
            if sph is not None:
                r = float(sph.get("radius", 0.5))
                visuals.append(("sphere", r, xyz))
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


def _expand(lo, hi, x, y, z):
    for i, c in enumerate((x, y, z)):
        if lo[i] is None or c < lo[i]:
            lo[i] = c
        if hi[i] is None or c > hi[i]:
            hi[i] = c


def _primitive_aabb(kind, data, oxyz):
    """Return the world AABB (lo, hi) of a primitive at origin oxyz (no rotation)."""
    ox, oy, oz = oxyz
    if kind == "box":
        w, h, l = data
        lo = [ox - w / 2, oy - h / 2, oz - l / 2]
        hi = [ox + w / 2, oy + h / 2, oz + l / 2]
        return lo, hi
    if kind == "cylinder":
        r, l = data
        lo = [ox - r, oy - r, oz - l / 2]
        hi = [ox + r, oy + r, oz + l / 2]
        return lo, hi
    if kind == "sphere":
        r = data
        lo = [ox - r, oy - r, oz - r]
        hi = [ox + r, oy + r, oz + r]
        return lo, hi
    return None


def compute_aabb(asset_dir):
    urdf = asset_dir / "model.urdf"
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
        for vis in visuals:
            kind = vis[0]
            ox = [vis[2][0] + lx, vis[2][1] + ly, vis[2][2] + lz]
            if kind == "mesh":
                mesh_file = asset_dir / vis[1]
                try:
                    with open(mesh_file, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if not line.startswith("v "):
                                continue
                            p = line.split()
                            _expand(lo, hi, float(p[1]) + ox[0], float(p[2]) + ox[1], float(p[3]) + ox[2])
                except OSError:
                    pass
            else:
                ab = _primitive_aabb(kind, vis[1], ox)
                if ab is not None:
                    _expand(lo, hi, ab[0][0], ab[0][1], ab[0][2])
                    _expand(lo, hi, ab[1][0], ab[1][1], ab[1][2])
    if lo[0] is None:
        return None
    center = [(lo[i] + hi[i]) / 2 for i in range(3)]
    dims = [hi[i] - lo[i] for i in range(3)]
    return center, dims


def main():
    dirs = sorted([p for p in ASSET_ROOT.iterdir() if p.is_dir()])
    for d in dirs:
        name = d.name
        result = compute_aabb(d)
        if result is None:
            dims = [0.0, 0.0, 0.0]
            print("%s: AABB unavailable, dims=[0,0,0]" % name)
        else:
            center, dims = result
        data = {
            "asset_dir": str(d),
            "center": [0.0, 0.0, 0.0],
            "dims": [round(x, 4) for x in dims],
            "rpy": [0.0, 0.0, 0.0],
        }
        out = ASSET_ROOT / (name + ".json")
        out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("wrote %s  dims=%s" % (out.name, data["dims"]))


if __name__ == "__main__":
    main()

"""Deterministic functional-front detection + application (no LLM / VLM).

Reads the compiled object model (parts + articulations) and returns the yaw
(degrees) to rotate the object about +y so its functional front faces +z.

The front is a *quantitative* conclusion, not a semantic guess:
  1. prismatic joint  -> drawer/slider opens along its axis;
  2. revolute joint   -> a door/lid panel's thin horizontal axis is the front;
  3. thin panel named screen/face/dial/display/front -> outward thin axis;
  4. a "seat" (horizontal slab) + a "backrest/back" (vertical panel) -> chair,
     front is opposite the back panel's horizontal offset.

Ambiguous / unsupported shapes return ``None`` so the asset is left unchanged
(safe: never rotate on a guess). The bake helpers rotate the materialized URDF
and the rest/swept AABBs together so downstream stays consistent.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

from sdk._core.v0.geometry_qc import (
    _aabb_center,
    _aabb_size,
    _mat4_vec3,
    _origin_to_mat4,
    compute_part_world_transforms,
    part_world_aabb,
)
from sdk._core.v0.assets import resolve_mesh_path
from sdk._core.v0.types import Mesh


# --- name lexicon -----------------------------------------------------------
def _hint(name: str) -> Optional[str]:
    """Classify a part name as front/seat/back via whole-word matching.

    ``_``/``-`` are treated as separators, and words are matched at boundaries so
    e.g. ``backspace`` does not match ``back`` and ``surface`` does not match
    ``face``.
    """
    n = name.lower().replace("_", " ").replace("-", " ")
    if re.search(r"\b(?:screen|display|dial|face|front|monitor|television)\b", n):
        return "front"
    if re.search(r"\b(?:seat|cushion)\b", n):
        return "seat"
    if re.search(r"\b(?:backrest|rear)\b", n) or re.search(r"\bback\b", n):
        return "back"
    return None


# --- geometry helpers -------------------------------------------------------
def _correction_yaw(front_dir) -> Optional[float]:
    """Map a cardinal front direction to the yaw (deg) that brings it to +z."""
    fx, fy, fz = front_dir
    if abs(fz) >= 0.9:
        return 0.0 if fz > 0 else 180.0
    if abs(fx) >= 0.9:
        return -90.0 if fx > 0 else 90.0
    return None  # vertical or non-cardinal


def _thin_horizontal_axis(dims) -> Optional[str]:
    """Return 'x' or 'z' if the box is clearly thin in exactly that horizontal axis."""
    w, h, d = dims
    if w < 0.45 * h and w < 0.45 * d:
        return "x"
    if d < 0.45 * w and d < 0.45 * h:
        return "z"
    return None


def _horizontal_slab(dims) -> bool:
    """True if thin in y (a flat horizontal surface like a seat)."""
    w, h, d = dims
    return h < 0.45 * w and h < 0.45 * d


def _vertical_panel(dims) -> bool:
    """True if tall in y and thin in one horizontal axis (a backrest/door panel)."""
    w, h, d = dims
    return h > 1.5 * w and h > 1.5 * d and (_thin_horizontal_axis(dims) is not None)


def _joint_type(j) -> str:
    jt = getattr(j, "articulation_type", None)
    if jt is None:
        return ""
    return str(getattr(jt, "value", jt)).lower()


def _load_obj_vertices(path):
    verts = []
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("v "):
            p = line.split()
            verts.append((float(p[1]), float(p[2]), float(p[3])))
    return verts


def _part_top_horizontal_center(part, tf, asset_root):
    """Horizontal (x, z) center of the TOP ~30% of a part's world vertices.

    For a chair this isolates the backrest (top of the leg/back frame) from the
    legs, so the back direction can be read even when the whole part's AABB is
    nearly symmetric.
    """
    for visual in list(getattr(part, "visuals", []) or []):
        geometry = getattr(visual, "geometry", None)
        if not isinstance(geometry, Mesh):
            continue
        fn = getattr(geometry, "filename", None)
        if not fn:
            continue
        path = resolve_mesh_path(fn, assets=asset_root)
        lv = _load_obj_vertices(path)
        if not lv:
            continue
        scale = tuple(geometry.scale) if getattr(geometry, "scale", None) else (1.0, 1.0, 1.0)
        origin = getattr(visual, "origin", None)
        o_tf = _origin_to_mat4(origin) if origin is not None else None
        sx, sy, sz = scale
        world = []
        for (vx, vy, vz) in lv:
            p = (vx * sx, vy * sy, vz * sz)
            if o_tf is not None:
                p = _mat4_vec3(o_tf, p)
            world.append(_mat4_vec3(tf, p))
        if not world:
            continue
        ys = [p[1] for p in world]
        ymax, ymin = max(ys), min(ys)
        ythr = ymax - 0.3 * (ymax - ymin)
        top = [p for p in world if p[1] >= ythr]
        if not top:
            continue
        cx = sum(p[0] for p in top) / len(top)
        cz = sum(p[2] for p in top) / len(top)
        return (cx, cz)
    return None


# --- main analysis ----------------------------------------------------------
def analyze_front(model, asset_root=None) -> Optional[float]:
    """Return the correction yaw (deg) or None if the front is not confidently known."""
    parts = getattr(model, "parts", None)
    if not isinstance(parts, list):
        parts = getattr(model, "links", None)
    joints = getattr(model, "articulations", None)
    if not isinstance(joints, list):
        joints = getattr(model, "joints", None)
    if not isinstance(parts, list) or not isinstance(joints, list):
        return None

    try:
        world = compute_part_world_transforms(model, {})
    except Exception:
        return None

    info: dict[str, dict] = {}
    for p in parts:
        name = getattr(p, "name", None)
        if not isinstance(name, str) or name not in world:
            continue
        aabb = part_world_aabb(p, world[name], asset_root=asset_root, prefer_collisions=False)
        if aabb is None:
            continue
        info[name] = {
            "name": name,
            "center": _aabb_center(aabb),
            "dims": _aabb_size(aabb),
            "hint": _hint(name),
            "part": p,
            "tf": world[name],
        }
    if not info:
        return None

    # 1) prismatic joint -> drawer/slider opens along its axis
    for j in joints:
        if _joint_type(j) != "prismatic":
            continue
        axis = getattr(j, "axis", (0.0, 0.0, 1.0))
        ax, ay, az = (float(v) for v in axis)
        if abs(ay) > 0.7:  # vertical slide is a lift, not a front
            continue
        n = math.sqrt(ax * ax + ay * ay + az * az)
        if n < 1e-9:
            continue
        ax, az = ax / n, az / n
        if abs(ax) >= abs(az):
            front = (1.0 if ax > 0 else -1.0, 0.0, 0.0)
        else:
            front = (0.0, 0.0, 1.0 if az > 0 else -1.0)
        return _correction_yaw(front)

    # 2) revolute joint -> door/lid child panel
    for j in joints:
        if _joint_type(j) not in ("revolute", "continuous"):
            continue
        child = getattr(j, "child", None)
        if not isinstance(child, str) or child not in info:
            continue
        d = info[child]
        thin = _thin_horizontal_axis(d["dims"])
        if thin is None:
            continue
        c = d["center"]
        if thin == "x":
            if abs(c[0]) < 1e-3:
                continue
            front = (1.0 if c[0] > 0 else -1.0, 0.0, 0.0)
        else:
            if abs(c[2]) < 1e-3:
                continue
            front = (0.0, 0.0, 1.0 if c[2] > 0 else -1.0)
        return _correction_yaw(front)

    # 3) thin panel named screen/face/dial/display/front
    for name, d in info.items():
        if d["hint"] != "front":
            continue
        thin = _thin_horizontal_axis(d["dims"])
        if thin is None:
            continue
        c = d["center"]
        if thin == "x":
            if abs(c[0]) < 1e-3:
                continue
            front = (1.0 if c[0] > 0 else -1.0, 0.0, 0.0)
        else:
            if abs(c[2]) < 1e-3:
                continue
            front = (0.0, 0.0, 1.0 if c[2] > 0 else -1.0)
        return _correction_yaw(front)

    # 4) chair: a seat (horizontal slab) + a tall "back" part -> the front is the
    #    side opposite the backrest. The backrest is the TOP portion of the back
    #    part (isolated from its legs), whose horizontal position is read from the
    #    mesh vertices so a nearly-symmetric frame AABB still resolves correctly.
    seat = None
    back = None
    for name, d in info.items():
        dims = d["dims"]
        if d["hint"] == "seat" and _horizontal_slab(dims):
            seat = d
        elif d["hint"] == "back" and dims[1] > 1.5 * max(dims[0], dims[2]):
            back = d
    if seat is not None and back is not None:
        top = _part_top_horizontal_center(back["part"], back["tf"], asset_root)
        if top is not None:
            dz = top[1] - seat["center"][2]
            dx = top[0] - seat["center"][0]
            if abs(dz) > 1e-3 or abs(dx) > 1e-3:
                if abs(dz) >= abs(dx):
                    front = (0.0, 0.0, -1.0 if dz > 0 else 1.0)
                else:
                    front = (-1.0 if dx > 0 else 1.0, 0.0, 0.0)
                return _correction_yaw(front)

    return None


# --- application helpers (bake + bbox rotation) -----------------------------
def rotate_aabb(
    center: Tuple[float, float, float],
    dims: Tuple[float, float, float],
    yaw_deg: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    th = math.radians(yaw_deg)
    c, s = math.cos(th), math.sin(th)
    hx, hy, hz = dims[0] / 2.0, dims[1] / 2.0, dims[2] / 2.0
    xs, ys, zs = [], [], []
    for dx in (-hx, hx):
        for dy in (-hy, hy):
            for dz in (-hz, hz):
                x = center[0] + dx
                y = center[1] + dy
                z = center[2] + dz
                xs.append(x * c + z * s)
                ys.append(y)
                zs.append(-x * s + z * c)
    mn = (min(xs), min(ys), min(zs))
    mx = (max(xs), max(ys), max(zs))
    new_center = ((mn[0] + mx[0]) / 2.0, (mn[1] + mx[1]) / 2.0, (mn[2] + mx[2]) / 2.0)
    new_dims = (mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2])
    return new_center, new_dims


def bake_urdf_yaw(urdf_path: Path, yaw_deg: float) -> Tuple[bool, str]:
    """Insert a root fixed joint rotating the whole robot about y by ``yaw_deg``."""
    yaw_rad = math.radians(yaw_deg)
    tree = ET.parse(urdf_path)
    root = tree.getroot()
    links = root.findall("link")
    joints = root.findall("joint")
    link_names = {l.get("name") for l in links}
    child_names = set()
    for j in joints:
        child = j.find("child")
        if child is not None:
            child_names.add(child.get("link"))
    roots = [n for n in link_names if n not in child_names]
    if len(roots) != 1:
        return False, f"expected exactly 1 root link, got {roots}"
    target = roots[0]

    base_name = "front_align_base"
    joint_name = "front_align_joint"
    existing_joints = {j.get("name") for j in joints}
    i = 0
    while base_name in link_names or joint_name in existing_joints:
        i += 1
        base_name = f"front_align_base_{i}"
        joint_name = f"front_align_joint_{i}"

    base = ET.SubElement(root, "link")
    base.set("name", base_name)
    jt = ET.SubElement(root, "joint")
    jt.set("name", joint_name)
    jt.set("type", "fixed")
    origin = ET.SubElement(jt, "origin")
    origin.set("xyz", "0 0 0")
    origin.set("rpy", f"0 {yaw_rad:.9f} 0")
    parent = ET.SubElement(jt, "parent")
    parent.set("link", base_name)
    child = ET.SubElement(jt, "child")
    child.set("link", target)
    tree.write(urdf_path, encoding="utf-8", xml_declaration=True)
    return True, target


def front_fix(model, urdf_path, rest_bbox, swept_bbox, *, asset_root=None):
    """Detect the front, bake into the URDF, rotate bboxes. Returns a summary dict."""
    corr = analyze_front(model, asset_root=asset_root)
    if corr is None:
        return {"correction_yaw": None, "applied": False}
    if abs(corr) < 1e-6:
        return {"correction_yaw": 0.0, "applied": False}

    ok, _ = bake_urdf_yaw(Path(urdf_path), corr)
    if not ok:
        return {"correction_yaw": None, "applied": False}

    new_rest = rotate_aabb(rest_bbox["center"], rest_bbox["dims"], corr)
    new_swept = rotate_aabb(swept_bbox["center"], swept_bbox["dims"], corr)
    return {
        "correction_yaw": corr,
        "applied": True,
        "rest_bbox": {"center": new_rest[0], "dims": new_rest[1]},
        "swept_bbox": {"center": new_swept[0], "dims": new_swept[1]},
    }


def front_fix_from_model_path(model_path, urdf_path, rest_bbox, swept_bbox, *, asset_root=None):
    """Load ``model_path`` (inside a fresh asset session) and run :func:`front_fix`."""
    from agent.compiler import load_model_globals
    from sdk._core.v0.assets import (
        AssetSession,
        activate_asset_session,
        asset_session_for_script,
    )

    model_path = Path(model_path).resolve()
    session = asset_session_for_script(model_path)
    if asset_root is not None:
        session = AssetSession(
            Path(asset_root).resolve(),
            inputs_root=session.inputs_root,
            mesh_subdir=session.mesh_subdir,
        )
    with activate_asset_session(session):
        globals_dict = load_model_globals(model_path)
        model = globals_dict.get("object_model")
        if model is None:
            return {"correction_yaw": None, "applied": False}
        return front_fix(model, urdf_path, rest_bbox, swept_bbox, asset_root=session.root)

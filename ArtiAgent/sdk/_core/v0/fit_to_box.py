"""Fit an articulated object into a target box (uniform scale + translate).

``fit_to_box`` enforces the geometry half of a layout ``--box`` constraint: it
uniformly scales an already-built model so its zero-pose world AABB fits inside
the target dims, then translates it so the AABB centre lands on the target
centre. Rotation is NOT applied — the model is expected to be authored already
in the y-up / +z-forward convention (front facing +z, up +y), matching
LayoutAgent's room frame.

Uniform scale is the only supported mode (per-axis stretch would require
mesh-converting cylinders/spheres and is intentionally out of scope). Translation
is applied by shifting the root part's geometry and every joint origin, which is
exact for the axis-aligned joint trees these generated models use.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional, Tuple

from .collision_helpers import _aabb_union
from .errors import ValidationError
from .geometry_qc import (
    compute_part_world_transforms,
    part_world_aabb,
)
from .types import Box, Cylinder, Mesh, Origin, Sphere

Vec3 = Tuple[float, float, float]


def _model_parts(model: object) -> list:
    parts = getattr(model, "parts", None)
    if isinstance(parts, list):
        return parts
    links = getattr(model, "links", None)
    return links if isinstance(links, list) else []


def _model_joints(model: object) -> list:
    joints = getattr(model, "articulations", None)
    if isinstance(joints, list):
        return joints
    links = getattr(model, "joints", None)
    return links if isinstance(links, list) else []


def _root_world_aabb(model: object, *, asset_root: object = None):
    """World AABB of the model at its zero pose (root frame)."""
    tfs = compute_part_world_transforms(model, {})
    boxes = []
    for part in _model_parts(model):
        tf = tfs.get(getattr(part, "name", None))
        if tf is None:
            continue
        aabb = part_world_aabb(part, tf, asset_root=asset_root, prefer_collisions=False)
        if aabb is not None:
            boxes.append(aabb)
    if not boxes:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    union = _aabb_union(boxes)
    return (
        ((union[0][0] + union[1][0]) * 0.5, (union[0][1] + union[1][1]) * 0.5, (union[0][2] + union[1][2]) * 0.5),
        (union[1][0] - union[0][0], union[1][1] - union[0][1], union[1][2] - union[0][2]),
    )


def _scale_geometry(geometry, s: float):
    if isinstance(geometry, Box):
        return Box(tuple(s * float(v) for v in geometry.size))
    if isinstance(geometry, Cylinder):
        return Cylinder(radius=s * float(geometry.radius), length=s * float(geometry.length))
    if isinstance(geometry, Sphere):
        return Sphere(radius=s * float(geometry.radius))
    if isinstance(geometry, Mesh):
        scale = geometry.scale if geometry.scale is not None else (1.0, 1.0, 1.0)
        return replace(geometry, scale=tuple(s * float(v) for v in scale))
    raise ValidationError(f"fit_to_box cannot scale geometry type: {type(geometry).__name__}")


def _scale_origin(origin: Origin, s: float) -> Origin:
    return replace(origin, xyz=tuple(s * float(v) for v in origin.xyz))


def _translate_origin(origin: Origin, delta: Vec3) -> Origin:
    return replace(origin, xyz=tuple(float(o) + float(d) for o, d in zip(origin.xyz, delta)))


def _root_part_names(model: object) -> set:
    parts = _model_parts(model)
    joints = _model_joints(model)
    children = {
        getattr(j, "child", None)
        for j in joints
        if isinstance(getattr(j, "child", None), str)
    }
    return {
        getattr(p, "name", None)
        for p in parts
        if isinstance(getattr(p, "name", None), str) and getattr(p, "name", None) not in children
    }


def fit_to_box(
    model: object,
    center: Vec3,
    dims: Vec3,
    *,
    uniform: bool = True,
    asset_root: object = None,
) -> object:
    """DISABLED (no-op).

    The old uniform-scale implementation (s = min(dims/cur_dims) + translate) was
    removed: a single wrong layout dimension (e.g. a 0.15 m-wide bicycle box)
    crushes the whole object to a fraction of its size. The box constraint is now
    a SOFT reference — the compile step reports the delta between the layout box
    and the object's actual box, and the designer LLM decides whether the actual
    size is acceptable (see CompileModelTool._box_delta_text in tool_layer.py).

    Kept as a no-op so existing generated model.py files that still call
    fit_to_box(...) keep compiling unchanged.
    """
    return model


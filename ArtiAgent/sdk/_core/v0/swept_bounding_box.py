"""Swept (joint-range) bounding box of an articulated object.

The *swept* bounding box is the axis-aligned box (in the root / world frame) that
contains the object's geometry over the FULL range of every joint's motion, not
just the current pose. A layout engine cares about this swept volume: a drawer
that slides open, a lid that lifts, or a wheel that spins all sweep a region
larger than the resting pose.

This is an assembly of existing primitives — no new kinematics:

- ``_joint_sample_values`` — the same per-joint sample set the QC overlap checks
  use (0, lower, upper, midpoint, or a fixed sweep for continuous joints);
- ``compute_part_world_transforms`` — forward kinematics for a pose;
- ``part_world_aabb`` — per-part world AABB;
- ``_aabb_union`` — union of axis-aligned boxes.

The result is expressed in the same y-up / +z-forward world frame LayoutAgent
uses, so ``(center, dims)`` can be dropped straight into a layout node.
"""

from __future__ import annotations

import itertools
from typing import List, Optional, Tuple

from .assets import resolve_asset_root
from .collision_helpers import _aabb_union
from .errors import ValidationError
from .geometry_qc import (
    _aabb_center,
    _aabb_size,
    _joint_sample_values,
    compute_part_world_transforms,
    part_world_aabb,
)

Vec3 = Tuple[float, float, float]


def joint_range_bounding_box(
    model: object,
    *,
    samples: Optional[int] = None,
    asset_root: object = None,
    prefer_collisions: bool = False,
) -> Tuple[Vec3, Vec3]:
    """Return ``(center, dims)`` swept by ``model`` across its full joint range.

    ``samples`` caps the number of pose combinations (default: enumerate the full
    Cartesian product of per-joint limit samples, which is exact and small for
    typical objects). ``asset_root`` overrides where mesh files are resolved from
    (defaults to the model's own asset context). ``prefer_collisions`` selects
    collision geometry over visual geometry for the AABBs.
    """
    joints = getattr(model, "articulations", None)
    if not isinstance(joints, list):
        joints = getattr(model, "joints", None)
    if not isinstance(joints, list):
        raise ValidationError("model must have an .articulations list")

    parts = getattr(model, "parts", None)
    if not isinstance(parts, list):
        parts = getattr(model, "links", None)
    if not isinstance(parts, list):
        raise ValidationError("model must have a .parts list")

    names: List[str] = []
    per_joint: List[List[object]] = []
    for joint in joints:
        name = getattr(joint, "name", None)
        if not isinstance(name, str):
            continue
        if getattr(joint, "mimic", None) is not None:
            continue
        names.append(name)
        per_joint.append(_joint_sample_values(joint))

    if not names:
        combos: List[Tuple[object, ...]] = [()]
    else:
        combos = list(itertools.product(*per_joint))
        if samples is not None:
            combos = combos[: max(1, int(samples))]

    resolved_root = resolve_asset_root(asset_root, model)

    swept: List[Tuple[Vec3, Vec3]] = []
    for combo in combos:
        pose = {names[i]: combo[i] for i in range(len(names))}
        tfs = compute_part_world_transforms(model, pose)
        for part in parts:
            part_name = getattr(part, "name", None)
            tf = tfs.get(part_name) if isinstance(part_name, str) else None
            if tf is None:
                continue
            aabb = part_world_aabb(
                part,
                tf,
                asset_root=resolved_root,
                prefer_collisions=prefer_collisions,
            )
            if aabb is not None:
                swept.append(aabb)

    if not swept:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    union = _aabb_union(swept)
    return _aabb_center(union), _aabb_size(union)

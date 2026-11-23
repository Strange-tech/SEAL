"""Real (joint-range) bounding box helpers shared by the `--emit-result` path and
the `real_bbox` tool."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from agent.compiler import load_model_globals
from sdk._core.v0.assets import (
    AssetSession,
    activate_asset_session,
    asset_session_for_script,
)
from sdk._core.v0.real_bounding_box import joint_range_bounding_box


def compute_model_real_bbox(
    model_path,
    *,
    asset_root=None,
    samples: Optional[int] = None,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Load ``model_path``'s ``object_model`` and return its ``(center, dims)``.

    Runs ``model.py`` inside a fresh asset session rooted at ``asset_root`` (so
    ``mesh_from_geometry`` writes its meshes there and ``joint_range_bounding_box``
    can resolve them), then computes the joint-range AABB.
    """
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
        object_model = globals_dict.get("object_model")
        if object_model is None:
            raise ValueError("model.py must define a top-level `object_model`")
        center, dims = joint_range_bounding_box(
            object_model,
            samples=samples,
            asset_root=session.root,
        )
    return center, dims


def compute_zero_pose_bbox(
    model_path,
    *,
    asset_root=None,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Return the object's ``(center, dims)`` at the zero (rest) pose.

    Unlike :func:`compute_model_real_bbox` (which sweeps the full joint range,
    so a drawer that slides open inflates the swept depth), this measures only
    the resting footprint. The ``--box`` orientation check compares against this
    static box so articulated travel cannot masquerade as a wrong orientation.
    """
    from sdk._core.v0.collision_helpers import _aabb_union
    from sdk._core.v0.geometry_qc import (
        _aabb_center,
        _aabb_size,
        compute_part_world_transforms,
        part_world_aabb,
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
            raise ValueError("model.py must define a top-level `object_model`")

        joints = getattr(model, "articulations", None)
        if not isinstance(joints, list):
            joints = getattr(model, "joints", None)
        parts = getattr(model, "parts", None)
        if not isinstance(parts, list):
            parts = getattr(model, "links", None)
        if not isinstance(joints, list) or not isinstance(parts, list):
            raise ValueError("model must have .articulations and .parts lists")

        # Zero pose: every non-mimic joint at 0.0 (matches the viewer's rest pose
        # clamp(0, lower, upper) and the authoring convention).
        names = []
        for j in joints:
            name = getattr(j, "name", None)
            if not isinstance(name, str):
                continue
            if getattr(j, "mimic", None) is not None:
                continue
            names.append(name)
        pose = {n: 0.0 for n in names}

        tfs = compute_part_world_transforms(model, pose)
        aabbs = []
        for part in parts:
            part_name = getattr(part, "name", None)
            tf = tfs.get(part_name) if isinstance(part_name, str) else None
            if tf is None:
                continue
            aabb = part_world_aabb(
                part, tf, asset_root=session.root, prefer_collisions=False
            )
            if aabb is not None:
                aabbs.append(aabb)

    if not aabbs:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    union = _aabb_union(aabbs)
    return _aabb_center(union), _aabb_size(union)

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

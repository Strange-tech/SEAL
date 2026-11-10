"""Scene graph -> OBB materialization and export (pure NumPy, no model dependency).

Materializes room.py's scene graph into OBBs (center/dims/theta), supporting:
- ``materialize_obbs``: nodes -> OBB list;
- ``obbs_to_obj``: export the OBB list to a Wavefront OBJ (one 8-vertex box mesh per OBB);
- ``project_obb_to_image``: reproject an OBB back into image space (2D AABB), used by compile's check against SAM3 boxes.

The OBB ``(center, dims, theta)`` convention is documented in :mod:`sdk.geometry` (dims=[w,h,l], theta in degrees).
"""

import os

import numpy as np

from .geometry import obb_corners
from .projection import project_points

# 8-vertex box (obb_corners corner order) -> 12 triangular faces
BOX_FACES = [
    (0, 1, 2), (2, 3, 0),   # z=-l/2 face
    (5, 4, 7), (7, 6, 5),   # z=+l/2 face
    (4, 0, 3), (3, 7, 4),   # x=-w/2 face
    (1, 5, 6), (6, 2, 1),   # x=+w/2 face
    (3, 2, 6), (6, 7, 3),   # y=+h/2 face
    (4, 5, 1), (1, 0, 4),   # y=-h/2 face
]


def materialize_obbs(graph):
    """scene graph -> OBB list.

    Each element is a dict: ``{"id", "type", "center", "dims", "theta"}``, where center/dims/theta are numpy (3,) floats.
    """
    obbs = []
    for n in graph.get("nodes", []):
        obbs.append({
            "id": n["id"],
            "type": n["type"],
            "center": np.asarray(n["C"], dtype=float),
            "dims": np.asarray(n["D"], dtype=float),
            "theta": np.asarray(n["theta"], dtype=float),
        })
    return obbs


def obbs_to_obj(obbs, path):
    """Export the OBB list to a Wavefront OBJ, returning the absolute path written.

    Each OBB is an ``o <id>`` object + a ``g <type>`` group, with 8 vertices + 12 triangular faces.
    """
    path = os.path.abspath(path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    lines = ["# layoutagent scene-graph export (OBB boxes)"]
    base = 1
    for obb in obbs:
        corners = obb_corners(obb["center"], obb["dims"], obb["theta"])
        lines.append(f"o {obb['id']}")
        lines.append(f"g {obb['type']}")
        for c in corners:
            lines.append(f"v {c[0]:.6f} {c[1]:.6f} {c[2]:.6f}")
        for f in BOX_FACES:
            lines.append(f"f {base + f[0]} {base + f[1]} {base + f[2]}")
        base += 8
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
    return path


def project_obb_to_image(obb, intrinsics, extrinsics):
    """OBB -> image-space 2D axis-aligned bounding box ``[u_min, v_min, u_max, v_max]``.

    obb may be a dict (with center/dims/theta) or a ``(center, dims, theta)`` tuple.
    Only the corners in front of the camera (z>0) are used; returns None if all corners are behind the camera.
    The returned pixel coordinates are in the intrinsics resolution (i.e. DA3's depth resolution).
    """
    if isinstance(obb, dict):
        center, dims, theta = obb["center"], obb["dims"], obb["theta"]
    else:
        center, dims, theta = obb
    corners = obb_corners(center, dims, theta)
    uv, z = project_points(corners, intrinsics, extrinsics)
    front = z > 0
    if not front.any():
        return None
    uv = uv[front]
    return np.array([uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max()])

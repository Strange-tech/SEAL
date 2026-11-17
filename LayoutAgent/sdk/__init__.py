"""layoutagent SDK: high-level API for the LLM to write room.py.

Layers:
- geometry: OBB geometry primitives (rotation, corners, points->OBB, intersection test)
- validation: relation-aware collision/floating detection + image reprojection consistency check (the compile tool's core)
- manhattan: East/North orthogonal basis estimation + orientation snap
- projection: depth backprojection + 3D->image projection
- fitting: upright OBB fitting, RANSAC plane, floor/wall detection
- scene: scene graph -> OBB materialization, OBJ export, OBB reprojection back to image
- alignment: room frame (y-up) -> camera frame rigid alignment (floor plane estimation)
"""
from . import alignment, fitting, geometry, manhattan, orientation, projection, scene, validation

__all__ = ["geometry", "manhattan", "projection", "validation", "fitting", "scene", "alignment", "orientation"]

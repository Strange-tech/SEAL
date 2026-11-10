"""Scene-graph data contract (single source of truth).

The scene graph is room.py's final product, with two top-level lists:

- ``nodes``: the scene's key elements. Each node's geometry:
    C     center     (x, y, z)
    D     size       (w, h, l)
    theta orientation (rx, ry, rz) — three successive rotations about x/y/z (degrees)
- ``edges``: spatial relations between nodes, type in EDGE_TYPES.

Coordinate convention (right-handed, y-up): +x right, +y up, +z toward the camera; the reference
horizontal surface (the largest horizontal plane in the shot: the floor in a wide shot, the
countertop/tabletop in a close-up) has its top at y=0, and the back wall (farthest wall) is at z=0.
Reconstruct only what is visible; if the floor is not in frame, do not declare a floor node. The
camera frame (DA3: x right / y down / z forward, camera at origin) converts to the room frame as
``room = [cam_x, -cam_y + h, -cam_z + D]``, where h is the camera height above the reference
horizontal surface and D is the camera-to-back-wall distance. NOTE: this flip is exact only for a
level camera; with camera pitch/roll, the SDK's alignment routine
(``sdk.alignment.estimate_room_transform``) does the exact rotation.
"""

# node types: wall and floor are structural elements, door/window are openings embedded in walls, object is a regular object.
NODE_TYPES = ("wall", "floor", "door", "window", "object")

# four spatial relations (see plan.md line 7)
EDGE_TYPES = (
    "embedded_in",  # embedded: a door/window inside a wall (OBBs intersect, legal)
    "adjacent",     # adjacent: horizontal relation, a small gap allowed
    "abuts",        # abuts: constrained horizontal/vertical relation (e.g. a cup on a table)
    "overlaps_ok",  # allowed overlap: OBBs intersect but it is legal (e.g. a chair tucked under a table)
)


def make_node(node_id, node_type, center, dims, orientation):
    """Construct a node. center/dims/orientation are each length-3 iterables."""
    return {
        "id": node_id,
        "type": node_type,
        "C": [float(v) for v in center],
        "D": [float(v) for v in dims],
        "theta": [float(v) for v in orientation],
    }


def make_edge(edge_type, src, dst):
    """Construct a directed edge (src -> dst)."""
    return {"type": edge_type, "src": src, "dst": dst}


def new_scene_graph():
    return {"nodes": [], "edges": []}

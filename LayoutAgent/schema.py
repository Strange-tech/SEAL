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
An object's intrinsic FRONT is its local +Z axis: at ``theta=[0,0,0]`` the front faces +Z (toward
the camera), and yaw ``ry`` rotates it in the horizontal plane (ry=90 -> +X, ry=180 -> -Z, ry=-90 -> -X).
Wall-mounted objects (TV, window, door, mirror, picture) must face INTO the room: set their ``theta``
equal to the supporting wall's ``theta`` so the object's front matches the wall's inward face.
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
    "supports",     # supports: one object supports another (cup on table, cabinet on floor, picture on wall); OBB faces in tight contact (no gap)
    "overlaps_ok",  # allowed overlap: OBBs intersect but it is legal (e.g. a chair tucked under a table)
)


def make_node(node_id, node_type, center, dims, orientation, klass=None):
    """Construct a node. center/dims/orientation are each length-3 iterables.

    ``klass`` (optional) is the canonical object class, used downstream to deduplicate
    identical instances (e.g. three "dining chair" nodes share the same class and are
    generated once, then instantiated at each node's own center/orientation).
    """
    node = {
        "id": node_id,
        "type": node_type,
        "C": [float(v) for v in center],
        "D": [float(v) for v in dims],
        "theta": [float(v) for v in orientation],
    }
    if klass:
        node["class"] = klass
    return node


def make_edge(edge_type, src, dst):
    """Construct a directed edge (src -> dst)."""
    return {"type": edge_type, "src": src, "dst": dst}


def new_scene_graph():
    return {"nodes": [], "edges": []}

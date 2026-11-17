"""Object orientation analysis (feeds the "front direction" back to the LLM via compile).

Convention (see prompts/docs.md): **front = local +Z axis** (the thickness/depth axis).
The door-facing normal of a cabinet and the sitting direction of a chair both run along
local +Z. When an object is upright (roll = pitch = 0), the horizontal projection of
local +Z in the world frame is the object's "front direction".

This module does NOT make hard reasonable/unreasonable verdicts; it only:
1. computes each object's front direction (world-space horizontal unit vector + yaw);
2. provides a reference direction (chair -> nearest table; wall-mounted furniture -> nearest wall's inward normal);
3. computes the angle between front and reference, tagging it aligned / perpendicular / reversed / no_reference for the LLM to judge;
4. validates wall orientation: by convention a wall's local +Z points indoors, decided by "which side has more objects"; if a wall's +Z points outward, it suggests flipping the yaw.

A wall's normal = local +Z (thickness axis); by convention +Z points indoors (inward normal),
and wall-mounted furniture's front should align with that inward normal.
"""

import numpy as np

from .geometry import rotation_matrix

# Name keywords (node ids are typically like "chair_0"; classified by id substring here)
CHAIR_KEYWORDS = ("chair", "stool", "seat", "sofa", "armchair", "couch", "bench")
TABLE_KEYWORDS = ("table", "desk")
# Wall-mounted furniture: its front should face indoors (the nearest wall's inward normal)
WALL_FURNITURE_KEYWORDS = ("cabinet", "wardrobe", "cupboard", "shelf", "bookcase",
                           "sideboard", "dresser", "bed", "tv", "television", "screen",
                           "monitor", "display", "mirror", "picture", "painting", "art")

VERDICT = {
    "aligned": "ok",
    "perpendicular": "perpendicular",
    "reversed": "reversed",
    "no_reference": "no reference",
}


def _contains(name, keywords):
    n = (name or "").lower()
    return any(k in n for k in keywords)


def _classify_category(node_id):
    if _contains(node_id, CHAIR_KEYWORDS):
        return "chair"
    if _contains(node_id, WALL_FURNITURE_KEYWORDS):
        return "wall_furniture"
    return "other"


def _valid_node(n):
    c = n.get("C")
    t = n.get("theta")
    return (isinstance(c, (list, tuple)) and len(c) == 3 and
            isinstance(t, (list, tuple)) and len(t) == 3)


def front_dir(theta):
    """Horizontal unit direction of the local +Z axis in the world frame (front)."""
    r = rotation_matrix(theta)
    f = r[:, 2]  # local +Z axis column
    h = np.array([f[0], 0.0, f[2]])
    norm = np.linalg.norm(h)
    if norm < 1e-9:
        return np.array([0.0, 0.0, 1.0])
    return h / norm


def _horizontal_dir(from_xy, to_xy):
    v = np.array([to_xy[0] - from_xy[0], 0.0, to_xy[1] - from_xy[1]], dtype=float)
    norm = np.linalg.norm(v)
    if norm < 1e-9:
        return None
    return v / norm


def _room_center(nodes):
    """Room center (horizontal xz): prefer the floor center, else the mean of all node centers."""
    floor = next((n for n in nodes if n.get("type") == "floor"), None)
    if floor is not None and _valid_node(floor):
        return (float(floor["C"][0]), float(floor["C"][2]))
    xs = [n["C"][0] for n in nodes if _valid_node(n)]
    zs = [n["C"][2] for n in nodes if _valid_node(n)]
    if not xs:
        return None
    return (float(np.mean(xs)), float(np.mean(zs)))


def _wall_adjacent_floor(wall, nodes):
    """Return the floor adjacent to a wall: the floor whose center is nearest the wall (geometric only, no edges).

    The indoor side of a wall always faces its adjacent floor. Using Euclidean distance to
    the nearest floor center is more robust than relying on the LLM-written
    supports/embedded_in edges (the LLM often drops edges or writes the wrong edge type).
    """
    floors = [n for n in nodes if n.get("type") == "floor" and _valid_node(n)]
    if not floors:
        return None
    return min(floors, key=lambda f: (f["C"][0] - wall["C"][0]) ** 2 + (f["C"][2] - wall["C"][2]) ** 2)


def _wall_indoor_sign(wall, nodes):
    """Whether the local +Z of a wall points indoors: +1 inward / -1 outward / 0 undecidable.

    Indoor side = the side containing the adjacent floor (the indoor side of a wall always
    faces its adjacent floor). Check which side of +Z the nearest floor center lies on;
    with no floor, fall back to "which side has more objects".
    """
    n = front_dir(wall["theta"])  # wall local +Z = normal
    floor = _wall_adjacent_floor(wall, nodes)
    if floor is not None:
        s = (floor["C"][0] - wall["C"][0]) * n[0] + (floor["C"][2] - wall["C"][2]) * n[2]
        if s > 1e-6:
            return 1
        if s < -1e-6:
            return -1
    pos = neg = 0
    for other in nodes:
        if other is wall or not _valid_node(other):
            continue
        s = (other["C"][0] - wall["C"][0]) * n[0] + (other["C"][2] - wall["C"][2]) * n[2]
        if s > 1e-6:
            pos += 1
        elif s < -1e-6:
            neg += 1
    if pos == neg:
        return 0
    return 1 if pos > neg else -1


def _wall_inward_dir(wall, nodes):
    """The indoor direction of a wall (horizontal unit vector): flip local +Z if it points outward."""
    n = front_dir(wall["theta"])
    if _wall_indoor_sign(wall, nodes) == -1:
        n = -n
    return n


def _edge_linked_wall(obj_id, walls, edges):
    """Find the wall linked to an object via a supports / embedded_in edge (object is src, wall is dst)."""
    wall_ids = {w["id"] for w in walls}
    for e in edges:
        if e.get("type") in ("supports", "embedded_in"):
            src, dst = e.get("src"), e.get("dst")
            if src == obj_id and dst in wall_ids:
                return next((w for w in walls if w["id"] == dst), None)
    return None


def _nearest_wall_inward(walls, obj, nodes):
    """The inward normal of the wall nearest an object (by perpendicular distance to the wall plane)."""
    best = None
    best_dist = None
    for wall in walls:
        n = _wall_inward_dir(wall, nodes)
        dvec = np.array([obj["C"][0] - wall["C"][0], 0.0, obj["C"][2] - wall["C"][2]])
        dist = abs(float(np.dot(n, dvec)))
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = n
    return best


def _front_yaw(front):
    """Horizontal unit vector -> yaw (degrees, [0, 360)). front = [sin(yaw), 0, cos(yaw)]."""
    return float(np.degrees(np.arctan2(front[0], front[2]))) % 360.0


def _dir_desc(v):
    """Horizontal unit vector -> readable heading (snapped to +-x / +-z)."""
    if abs(v[0]) >= abs(v[2]):
        return "+x" if v[0] >= 0 else "-x"
    return "+z" if v[2] >= 0 else "-z"


def analyze_orientation(graph):
    """Analyze every object node's front direction, returning a list of observations.

    Each observation:
        id, category, front, front_yaw, ref_desc, ref, angle_deg, verdict
    verdict in {aligned, perpendicular, reversed, no_reference}.
    """
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    center = _room_center(nodes)
    objects = [n for n in nodes if n.get("type") == "object" and _valid_node(n)]
    walls = [n for n in nodes if n.get("type") == "wall" and _valid_node(n)]
    tables = [n for n in objects if _contains(n["id"], TABLE_KEYWORDS)]

    observations = []
    for n in objects:
        front = front_dir(n["theta"])
        cat = _classify_category(n["id"])
        ref = None
        ref_desc = "no clear reference"

        if cat == "chair":
            # toward the nearest table; fall back to the room center when there is no table
            nearest = None
            best = None
            for t in tables:
                if t["id"] == n["id"]:
                    continue
                d = (n["C"][0] - t["C"][0]) ** 2 + (n["C"][2] - t["C"][2]) ** 2
                if best is None or d < best:
                    best = d
                    nearest = t
            if nearest is not None:
                ref = _horizontal_dir((n["C"][0], n["C"][2]),
                                      (nearest["C"][0], nearest["C"][2]))
                ref_desc = "toward table " + nearest["id"]
            elif center is not None:
                ref = _horizontal_dir((n["C"][0], n["C"][2]), center)
                ref_desc = "toward room center (no table)"
        elif cat == "wall_furniture":
            wall = _edge_linked_wall(n["id"], walls, edges)
            if wall is not None:
                ref = _wall_inward_dir(wall, nodes)
                ref_desc = "toward the indoor side of " + wall["id"]
            else:
                ref = _nearest_wall_inward(walls, n, nodes)
                if ref is not None:
                    ref_desc = "toward the inward normal of the nearest wall"
                elif center is not None:
                    ref = _horizontal_dir((n["C"][0], n["C"][2]), center)
                    ref_desc = "toward room center (no wall)"

        angle = None
        verdict = "no_reference"
        if ref is not None:
            dot = float(np.clip(np.dot(front, ref), -1.0, 1.0))
            angle = float(np.degrees(np.arccos(dot)))
            if angle < 45.0:
                verdict = "aligned"
            elif angle > 135.0:
                verdict = "reversed"
            else:
                verdict = "perpendicular"

        observations.append({
            "id": n["id"],
            "category": cat,
            "front": [float(x) for x in front],
            "front_yaw": _front_yaw(front),
            "ref_desc": ref_desc,
            "ref": ([float(x) for x in ref] if ref is not None else None),
            "angle_deg": angle,
            "verdict": verdict,
        })
    return observations


def format_orientation_report(observations):
    """Turn orientation observations into a readable report for the LLM. Empty string when none."""
    if not observations:
        return ""
    lines = ["[orientation] front-direction check (judge whether each orientation is reasonable):"]
    for o in observations:
        front = _dir_desc(o["front"])
        if o["verdict"] == "no_reference":
            lines.append("  - " + o["id"] + ": front faces " + front + " (" + o["ref_desc"] + ", not judged)")
        else:
            lines.append(
                "  - " + o["id"] + ": front faces " + front + ", " + o["ref_desc"] + ", "
                "deviation " + format(o["angle_deg"], ".0f") + " deg -> " + VERDICT[o["verdict"]]
            )
    return "\n".join(lines)


def orientation_warnings(observations):
    """Turn clearly suspicious orientations (reversed / perpendicular) into warnings for compile."""
    out = []
    for o in observations:
        if o["verdict"] == "reversed":
            out.append("orientation: " + o["id"] + " front faces away from " + o["ref_desc"]
                       + " (deviation " + format(o["angle_deg"], ".0f") + " deg), please confirm the orientation")
        elif o["verdict"] == "perpendicular":
            out.append("orientation: " + o["id"] + " front is sideways to " + o["ref_desc"]
                       + " (deviation " + format(o["angle_deg"], ".0f") + " deg), please confirm the orientation")
    return out


def analyze_walls(graph):
    """Validate each wall's orientation (convention: wall +Z points indoors), returning observations.

    Each observation: id, front, indoor_sign (+1/-1/0), verdict in {inward, outward, ambiguous}.
    """
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    walls = [n for n in nodes if n.get("type") == "wall" and _valid_node(n)]
    out = []
    for w in walls:
        sign = _wall_indoor_sign(w, nodes)
        verdict = "inward" if sign == 1 else ("outward" if sign == -1 else "ambiguous")
        out.append({
            "id": w["id"],
            "front": [float(x) for x in front_dir(w["theta"])],
            "indoor_sign": sign,
            "verdict": verdict,
        })
    return out


def wall_orientation_warnings(observations):
    """Turn walls whose +Z points outward into warnings (convention: it should point indoors)."""
    out = []
    for o in observations:
        if o["verdict"] == "outward":
            out.append("orientation: " + o["id"] + " local +Z points outdoors (should point indoors), "
                       "add 180 deg to theta yaw")
    return out


def format_wall_report(observations):
    """Turn wall orientation observations into a readable report for the LLM. Empty string when none."""
    if not observations:
        return ""
    lines = ["[wall-orientation] wall orientation check (convention: wall +Z points indoors):"]
    for o in observations:
        d = _dir_desc(o["front"])
        if o["verdict"] == "inward":
            lines.append("  - " + o["id"] + ": +Z faces " + d + " (indoor) ok")
        elif o["verdict"] == "outward":
            lines.append("  - " + o["id"] + ": +Z faces " + d + " (outdoor) -> flip yaw")
        else:
            lines.append("  - " + o["id"] + ": +Z faces " + d + " (indoor side undecidable)")
    return "\n".join(lines)

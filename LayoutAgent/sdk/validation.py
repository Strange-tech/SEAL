"""Relation-aware scene-graph validation (called by the ``compile`` tool).

Returns three tiers of diagnostics ``(failures, warnings, notes)``:
- failure: must be fixed to zero (structural errors, non-exempt collisions, floating objects)
- warning: better fixed (relation/geometry contradiction, or OBB reprojection deviating too far from the SAM3 box)
- note: informational (safe to ignore)

Exemption rules (see plan.md line 15, "embedded/overlap relations are exempt"):
- ``embedded_in`` / ``overlaps_ok``: OBB intersection is legal, so the collision check is skipped
- the ``src`` of a ``supports`` edge: supported, so the floating check is skipped
- ``floor`` is the reference surface and never participates in collision; ``door``/``window`` are embedded in walls and skip the floating check

Image-consistency check ``validate_image_reprojection``: reprojects each object OBB back to the image and computes the IoU against SAM3's 2D boxes. A deviation (1 - IoU) below the threshold is ok, otherwise a warning.
"""

import numpy as np

import schema
from .alignment import estimate_room_transform
from .geometry import obbs_overlap, obbs_gap
from .scene import project_obb_to_image


def _bottom_y(n):
    return n["C"][1] - n["D"][1] / 2.0


def _floor_top(nodes):
    for n in nodes:
        if n["type"] == "floor":
            # assume the floor has no rotation; top face y = C[1] + D[1]/2
            return n["C"][1] + n["D"][1] / 2.0
    return None


def _iou(a, b):
    """IoU of two xyxy boxes."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(0.0, (b[2] - b[0]) * (b[3] - b[1]))
    union = area_a + area_b - inter
    return inter / union if union > 1e-9 else 0.0


def _collision_box(node):
    """Return the OBB tuple (C, D, theta) to use for collision.

    Prefers the node's ``swept_bbox`` (the swept joint-range AABB, already in world
    coords) so articulated objects reserve their full motion envelope; otherwise
    falls back to the rest box (C/D/theta) for static objects.
    """
    rb = node.get("swept_bbox")
    if isinstance(rb, dict) and rb.get("center") and rb.get("dims"):
        return (rb["center"], rb["dims"], node.get("theta", [0.0, 0.0, 0.0]))
    return (node.get("C"), node.get("D"), node.get("theta", [0.0, 0.0, 0.0]))


def validate_scene_graph(graph, floor_tolerance=0.05, supports_tolerance=0.02):
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    failures, warnings, notes = [], [], []

    # ---- structural checks ----
    ids = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            failures.append(f"nodes[{i}] is not a dict")
            continue
        nid = n.get("id")
        if not isinstance(nid, str) or not nid:
            failures.append(f"nodes[{i}].id must be a non-empty string")
        elif nid in ids:
            failures.append(f"duplicate node id: {nid!r}")
        else:
            ids.add(nid)
        if n.get("type") not in schema.NODE_TYPES:
            failures.append(f"nodes[{i}].type={n.get('type')!r} not in {schema.NODE_TYPES}")
        for k in ("C", "D", "theta"):
            v = n.get(k)
            if not (isinstance(v, (list, tuple)) and len(v) == 3):
                failures.append(f"nodes[{i}].{k} must be a length-3 list")
        d = n.get("D")
        if isinstance(d, (list, tuple)) and len(d) == 3 and any(x < 0 for x in d):
            failures.append(f"nodes[{i}].D must be non-negative")

    for j, e in enumerate(edges):
        if not isinstance(e, dict):
            failures.append(f"edges[{j}] is not a dict")
            continue
        if e.get("type") not in schema.EDGE_TYPES:
            failures.append(f"edges[{j}].type={e.get('type')!r} not in {schema.EDGE_TYPES}")
        if e.get("src") not in ids or e.get("dst") not in ids:
            failures.append(f"edges[{j}] references unknown node id")

    # skip geometry checks on structural errors (avoid KeyError)
    if failures:
        return failures, warnings, notes

    node_map = {n["id"]: n for n in nodes}

    # ---- exemption sets ----
    exempt = set()      # embedded_in / overlaps_ok: OBB intersection is legal
    supported = set()   # supports src: supported, skip the floating check
    for e in edges:
        pair = frozenset((e["src"], e["dst"]))
        if e["type"] in ("embedded_in", "overlaps_ok"):
            exempt.add(pair)
        if e["type"] == "supports":
            supported.add(e["src"])

    # ---- collision check (floor excluded; embedded_in/overlaps_ok exempt) ----
    for i in range(len(nodes)):
        a = nodes[i]
        if a["type"] == "floor":
            continue
        for j in range(i + 1, len(nodes)):
            b = nodes[j]
            if b["type"] == "floor":
                continue
            if frozenset((a["id"], b["id"])) in exempt:
                continue
            if obbs_overlap(_collision_box(a), _collision_box(b)):
                failures.append(f"collision: {a['id']} vs {b['id']}")

    # ---- floating check (wall/object must sit on the floor; door/window embedded in walls are skipped) ----
    floor_top = _floor_top(nodes)
    if floor_top is None:
        notes.append("no floor node; floating check skipped")
    else:
        for n in nodes:
            if n["type"] in ("floor", "door", "window"):
                continue
            if n["id"] in supported:
                continue
            bottom = _bottom_y(n)
            if bottom > floor_top + floor_tolerance:
                failures.append(
                    f"floating: {n['id']} bottom={bottom:.3f} above floor top={floor_top:.3f}"
                )

    # ---- supports contact (failure): src must sit tightly against dst ----
    for e in edges:
        if e["type"] == "supports":
            a, b = node_map[e["src"]], node_map[e["dst"]]
            gap = obbs_gap((a["C"], a["D"], a["theta"]), (b["C"], b["D"], b["theta"]))
            if gap > supports_tolerance:
                failures.append(
                    f"supports but not in contact: {e['src']} vs {e['dst']} (gap={gap:.3f} m)"
                )

    # ---- relation-geometry consistency (warning) ----
    for e in edges:
        if e["type"] == "overlaps_ok":
            a, b = node_map[e["src"]], node_map[e["dst"]]
            if not obbs_overlap((a["C"], a["D"], a["theta"]), (b["C"], b["D"], b["theta"])):
                warnings.append(f"overlaps_ok but no overlap: {e['src']} vs {e['dst']}")

    return failures, warnings, notes


# def validate_image_reprojection(graph, reconstruction, boxes, image_size=None,
#                                 iou_threshold=0.5, extrinsics_scene=None):
#     """Reproject object-node OBBs back to the image and compare them against SAM3 boxes; returns ``(warnings, notes)``.

#     Args:
#     - ``reconstruction``: Reconstruction (holds intrinsics/extrinsics and the depth width/height);
#     - ``boxes``: ``{name: [x1,y1,x2,y2]}`` (SAM3 boxes, original-resolution xyxy);
#     - ``image_size``: ``(W, H)`` original image size, used to scale the depth-resolution projection box to the original image;
#     - ``iou_threshold``: deviation threshold, ``dev = 1 - best IoU``; ``dev >= threshold`` raises a warning;
#     - ``extrinsics_scene``: room-frame -> camera-frame w2c transform (3x4). When omitted, it is estimated with
#       ``estimate_room_transform`` from the reference horizontal surface and, when available, a confident
#       back wall (see :mod:`sdk.alignment`).

#     The room frame (y-up) differs from the camera frame (y-down), so the room-frame extrinsic must be applied
#     before reprojection; the up direction is fixed by the reference horizontal surface, while depth and x-offset
#     are solved image-anchored (yaw=0) or from a confident back wall.
#     """
#     warnings, notes = [], []
#     objects = [n for n in graph.get("nodes", []) if n.get("type") == "object"]
#     if not objects:
#         notes.append("image reprojection check skipped: no object nodes")
#         return warnings, notes

#     K = np.asarray(reconstruction.intrinsics, dtype=float)
#     if extrinsics_scene is None:
#         extrinsics_scene = estimate_room_transform(reconstruction, graph)
#         if extrinsics_scene is None:
#             return [], ["image reprojection check skipped: no reference horizontal surface detected"]
#     ext = np.asarray(extrinsics_scene, dtype=float)
#     dw, dh = reconstruction.width, reconstruction.height
#     if image_size is not None and dw > 0 and dh > 0:
#         sx = image_size[0] / dw
#         sy = image_size[1] / dh
#     else:
#         sx = sy = 1.0

#     box_list = [(name, np.asarray(b, dtype=float)) for name, b in (boxes or {}).items()]

#     for n in objects:
#         obb = {"center": n["C"], "dims": n["D"], "theta": n["theta"]}
#         bbox = project_obb_to_image(obb, K, ext)
#         if bbox is None:
#             warnings.append(f"reprojection: {n['id']} behind camera (no 2D projection)")
#             continue
#         bbox = bbox * np.array([sx, sy, sx, sy])
#         best_iou, best_name = 0.0, None
#         for name, b in box_list:
#             iou = _iou(bbox, b)
#             if iou > best_iou:
#                 best_iou, best_name = iou, name
#         dev = 1.0 - best_iou
#         if best_name is None:
#             warnings.append(
#                 f"reprojection: {n['id']} no SAM3 detection (best IoU={best_iou:.2f})"
#             )
#         elif best_iou < iou_threshold:
#             warnings.append(
#                 f"reprojection: {n['id']} vs SAM3 {best_name!r} IoU={best_iou:.2f} "
#                 f"(dev {dev:.2f} >= {iou_threshold:.2f})"
#             )
#         else:
#             notes.append(
#                 f"[ok] {n['id']} vs SAM3 {best_name!r} IoU={best_iou:.2f} (dev {dev:.2f})"
#             )
#     return warnings, notes

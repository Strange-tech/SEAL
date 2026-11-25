"""Cross-agent contract for SEAL.

Single source of truth for the JSON messages exchanged between LayoutAgent,
ArtiAgent and BaseAgent. Every message carries ``schema_version`` so a change in
one project fails loudly instead of silently corrupting a handoff.

Messages:
  - SceneGraph       (LayoutAgent -> BaseAgent): the room's nodes/edges.
  - PlacementRequest (BaseAgent -> ArtiAgent): one object's box + label + image.
  - AssetResult      (ArtiAgent -> BaseAgent): asset_dir + rest_bbox + swept_bbox.
"""

from __future__ import annotations

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- #
# field helpers
# --------------------------------------------------------------------------- #
def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_version(errors: list, data) -> None:
    if not isinstance(data, dict):
        errors.append("message must be a JSON object")
        return
    v = data.get("schema_version")
    if v is None:
        errors.append("schema_version: missing")
    elif v != SCHEMA_VERSION:
        errors.append("schema_version: got %r, expected %d" % (v, SCHEMA_VERSION))


def _check_vec3(errors: list, data: dict, field: str, required: bool = True) -> None:
    v = data.get(field)
    if v is None:
        if required:
            errors.append("%s: missing" % field)
        return
    if not isinstance(v, (list, tuple)) or len(v) != 3 or not all(_is_num(x) for x in v):
        errors.append("%s: expected 3 numbers, got %r" % (field, v))


def _check_str(errors: list, data: dict, field: str, required: bool = True) -> None:
    v = data.get(field)
    if v in (None, ""):
        if required:
            errors.append("%s: missing" % field)
        return
    if not isinstance(v, str):
        errors.append("%s: expected string, got %s" % (field, type(v).__name__))


# --------------------------------------------------------------------------- #
# validators — each returns a list of error strings (empty == valid)
# --------------------------------------------------------------------------- #
def validate_scene_graph(data) -> list:
    errors: list = []
    _check_version(errors, data)
    if not isinstance(data, dict):
        return errors

    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        errors.append("nodes: expected a list")
    else:
        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                errors.append("nodes[%d]: not an object" % i)
                continue
            _check_str(errors, n, "id")
            _check_str(errors, n, "type")
            _check_vec3(errors, n, "C")
            _check_vec3(errors, n, "D")
            _check_vec3(errors, n, "theta", required=False)

    edges = data.get("edges")
    if not isinstance(edges, list):
        errors.append("edges: expected a list")
    else:
        for i, e in enumerate(edges):
            if not isinstance(e, dict):
                errors.append("edges[%d]: not an object" % i)
                continue
            _check_str(errors, e, "type")
            _check_str(errors, e, "src")
            _check_str(errors, e, "dst")
    return errors


def validate_placement_request(data) -> list:
    errors: list = []
    _check_version(errors, data)
    if not isinstance(data, dict):
        return errors

    _check_str(errors, data, "object_id")
    _check_str(errors, data, "label")
    _check_str(errors, data, "class", required=False)

    box = data.get("box")
    if not isinstance(box, dict):
        errors.append("box: expected an object {center, dims, rpy}")
    else:
        _check_vec3(errors, box, "center")
        _check_vec3(errors, box, "dims")
        _check_vec3(errors, box, "rpy", required=False)
    return errors


def validate_asset_result(data) -> list:
    errors: list = []
    _check_version(errors, data)
    if not isinstance(data, dict):
        return errors

    _check_str(errors, data, "asset_dir")
    _check_vec3(errors, data, "center")
    _check_vec3(errors, data, "rpy")
    for field in ("rest_bbox", "swept_bbox"):
        bb = data.get(field)
        if bb is None:
            errors.append("%s: missing" % field)
        elif not isinstance(bb, dict):
            errors.append("%s: expected an object {center, dims}" % field)
        else:
            _check_vec3(errors, bb, "center")
            _check_vec3(errors, bb, "dims")
    return errors


# --------------------------------------------------------------------------- #
# builders — construct a versioned message dict
# --------------------------------------------------------------------------- #
def scene_graph(nodes, edges) -> dict:
    return {"schema_version": SCHEMA_VERSION, "nodes": nodes, "edges": edges}


def placement_request(object_id, label, box, klass=None, image=None) -> dict:
    req = {"schema_version": SCHEMA_VERSION, "object_id": object_id, "label": label, "box": box}
    if klass:
        req["class"] = klass
    if image:
        req["image"] = image
    return req


def asset_result(asset_dir, center, rpy, rest_bbox, swept_bbox) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "asset_dir": str(asset_dir),
        "center": list(center),
        "rpy": list(rpy),
        "rest_bbox": {"center": list(rest_bbox["center"]), "dims": list(rest_bbox["dims"])},
        "swept_bbox": {"center": list(swept_bbox["center"]), "dims": list(swept_bbox["dims"])},
    }

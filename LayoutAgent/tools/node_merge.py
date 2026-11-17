"""Deterministic node merge for LayoutAgent compile.

Even after ``resolve_overlaps`` collapses overlapping/nested SAM3 masks into one
semantic mask, the scene graph can still contain two object nodes that were
backprojected from the SAME (now merged) mask — e.g. a carafe node and a dripper
node stacked on top of it. This module collapses those into a single node.

Linking a node to its mask:
  * an optional ``mask`` field on the object node (the SAM3 mask name it was
    backprojected from), resolved through ``state.mask_redirect``;
  * fallback: the node id with ``_`` -> space normalization matched exactly against
    the redirect keys / values and the current mask names.

Groups of object nodes that resolve to the same final mask are merged. The merged
OBB is the axis-aligned bounding box of the group's OBBs (theta reset to 0). The
merge is idempotent: the kept node records the final mask name, so a second pass is
a no-op.
"""

import json
import re

import numpy as np

from sdk.geometry import aabb


def _norm(name):
    return str(name).strip().replace("_", " ")


def _strip_index(name):
    """Drop a trailing SAM3 ``_<digits>`` suffix: ``coffee carafe_1`` -> ``coffee carafe``."""
    return re.sub(r"_\d+$", "", str(name)).strip()


def resolve_final_mask(state, node):
    """Return the final (post-merge) mask name for an object node, or None.

    Resolution order for a node's ``mask`` field: exact redirect key -> exact current
    mask name -> suffix-stripped match against redirect keys/values and mask names ->
    the literal value itself. Two nodes that resolve to the same name are merged.
    """
    redirect = getattr(state, "mask_redirect", {}) or {}
    masks = getattr(state, "masks", {}) or {}

    m = node.get("mask")
    if isinstance(m, str) and m:
        m = m.strip()
        if m in redirect:
            return redirect[m]
        if m in masks:
            return m
        sm = _strip_index(m)
        if sm != m:
            for k, v in redirect.items():
                if _strip_index(k) == sm or _strip_index(v) == sm:
                    return v
            for name in masks:
                if _strip_index(name) == sm:
                    return name
        return m

    # fallback: node id -> redirect key / mask name (exact and suffix-stripped)
    nid = node.get("id")
    for c in (nid, _norm(nid), _strip_index(nid)):
        if not c:
            continue
        if c in redirect:
            return redirect[c]
        if c in masks:
            return c
        for k, v in redirect.items():
            if _strip_index(k) == c or _strip_index(v) == c or _norm(k) == c:
                return v
        for name in masks:
            if _strip_index(name) == c or _norm(name) == c:
                return name
    return None


def _merge_group(group):
    """Merge several object nodes into one (AABB union of their OBBs)."""
    lo = None
    hi = None
    for n in group:
        mn, mx = aabb(n["C"], n["D"], n["theta"])
        lo = mn if lo is None else np.minimum(lo, mn)
        hi = mx if hi is None else np.maximum(hi, mx)
    keep = dict(group[0])  # keep the first node's id/type/extra fields
    keep["C"] = [round(float(v), 6) for v in ((lo + hi) / 2.0)]
    keep["D"] = [round(float(v), 6) for v in (hi - lo)]
    keep["theta"] = [0, 0, 0]
    return keep


def merge_contained_nodes(graph, state):
    """Merge object nodes that map to the same final mask.

    Returns ``(graph, summary_lines)``; ``summary_lines`` is empty when nothing was
    merged. The input graph is not mutated.
    """
    nodes = list(graph.get("nodes", []))
    edges = list(graph.get("edges", []))
    redirect = getattr(state, "mask_redirect", {}) or {}
    masks = getattr(state, "masks", {}) or {}
    if not (redirect or masks):
        return graph, []

    groups = {}   # final mask -> list of nodes
    order = []    # first-seen order of final masks
    for n in nodes:
        if n.get("type") != "object":
            continue
        fm = resolve_final_mask(state, n)
        if fm is None:
            continue
        if fm not in groups:
            groups[fm] = []
            order.append(fm)
        groups[fm].append(n)

    merged_by_final = {}  # final mask -> kept merged node (only groups with >1)
    removed = set()
    id_replace = {}
    summary = []
    for fm in order:
        grp = groups[fm]
        if len(grp) < 2:
            continue
        keep = _merge_group(grp)
        keep["mask"] = fm
        merged_by_final[fm] = keep
        for n in grp[1:]:
            removed.add(n["id"])
            id_replace[n["id"]] = keep["id"]
        summary.append(
            f"merged nodes {[n['id'] for n in grp]} -> {keep['id']!r} (mask {fm!r})"
        )

    if not summary:
        return graph, []

    final_nodes = []
    emitted = set()
    for n in nodes:
        if n["id"] in removed:
            continue
        if n.get("type") == "object":
            fm = resolve_final_mask(state, n)
            if fm in merged_by_final:
                if fm not in emitted:
                    final_nodes.append(merged_by_final[fm])
                    emitted.add(fm)
                continue
        final_nodes.append(n)

    seen = set()
    new_edges = []
    for e in edges:
        src = id_replace.get(e["src"], e["src"])
        dst = id_replace.get(e["dst"], e["dst"])
        if src == dst:
            continue
        key = (e["type"], src, dst)
        if key in seen:
            continue
        seen.add(key)
        new_edges.append({"type": e["type"], "src": src, "dst": dst})

    return {"nodes": final_nodes, "edges": new_edges}, summary


def graph_to_py(graph):
    """Serialize a scene-graph dict back to a canonical ``build_scene_graph()`` module."""
    nodes = json.dumps(graph.get("nodes", []), indent=4, ensure_ascii=False)
    edges = json.dumps(graph.get("edges", []), indent=4, ensure_ascii=False)
    return (
        "from __future__ import annotations\n\n\n"
        "def build_scene_graph() -> dict:\n"
        "    return {\n"
        f'        "nodes": {nodes},\n'
        f'        "edges": {edges},\n'
        "    }\n"
    )

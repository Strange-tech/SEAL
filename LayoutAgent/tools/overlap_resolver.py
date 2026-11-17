"""Overlapping-mask resolver for LayoutAgent.

SAM3 is open-set: two different text prompts often segment the *same* physical
object (or two parts of one object — a carafe and the dripper sitting on top of
it, a cup and its handle, a pot and its lid) as two near-identical masks. If we
backproject those independently, the scene graph ends up with two duplicate OBBs
for one object.

This module:

  1. detects pairs of cached SAM3 masks where one is mostly contained in the
     other (containment = intersection / min(area_a, area_b) exceeds
     ``SEAL_OVERLAP_CONTAINMENT``),
  2. asks a VLM (via a ``Provider``) to decide whether the pair is actually the
     same object / parts of one object,
  3. on a "same" verdict, merges the pair into ONE semantic mask (union mask +
     union box) before any ``backproject_obb`` call, and records a redirect so
     ``backproject_obb`` on an old name still resolves to the merged mask.

The merge is deterministic and idempotent: it runs once per ``PerceptionState``
(either lazily on the first ``backproject_obb`` or explicitly via the
``resolve_overlaps`` tool) and never re-runs.
"""

import base64
import io
import json
import os

import numpy as np

OVERLAP_CONTAINMENT_THRESHOLD = float(os.environ.get("SEAL_OVERLAP_CONTAINMENT", "0.9"))


def mask_iou(a, b):
    """IoU between two boolean masks."""
    a = np.asarray(a, dtype=bool)
    b = np.asarray(b, dtype=bool)
    inter = int((a & b).sum())
    union = int((a | b).sum())
    return inter / union if union else 0.0


def mask_containment(a, b):
    """Fraction of the smaller mask that lies inside the other (intersection / min area).

    Unlike IoU, this does not depend on the size ratio of the two masks: a small
    mask fully contained in a large one gives ~1.0, and two near-identical masks
    also give ~1.0, so a single threshold catches both the "part of one object"
    and the "duplicate segment" cases.
    """
    a = np.asarray(a, dtype=bool)
    b = np.asarray(b, dtype=bool)
    inter = int((a & b).sum())
    denom = min(int(a.sum()), int(b.sum()))
    return inter / denom if denom else 0.0


def find_overlapping_pairs(masks):
    """Return [(name_a, name_b, containment), ...] for pairs where one mask is mostly
    contained in the other (containment >= threshold), sorted by containment desc."""
    names = list(masks.keys())
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            cont = mask_containment(masks[names[i]], masks[names[j]])
            if cont >= OVERLAP_CONTAINMENT_THRESHOLD:
                pairs.append((names[i], names[j], cont))
    pairs.sort(key=lambda t: -t[2])
    return pairs


def union_box(b1, b2):
    return [
        min(float(b1[0]), float(b2[0])),
        min(float(b1[1]), float(b2[1])),
        max(float(b1[2]), float(b2[2])),
        max(float(b1[3]), float(b2[3])),
    ]


def _pil_to_data_url(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{data}"


_VLM_PROMPT = (
    'Two objects were detected with overlapping or nested masks: "{a}" and "{b}".\n'
    "Look at the image region and decide whether they are actually the SAME physical object "
    "or different parts of one object (for example a carafe and its dripper/lid, a cup and its "
    "handle, a pot and its lid) rather than two separate objects.\n"
    'Reply in exactly one line: "same|<short merged name>" if they are one object or parts of '
    'one object, or "separate" if they are two distinct objects.'
)


def _vlm_check(provider, image, name_a, name_b, box):
    """Ask the VLM whether two overlapping masks are one object/parts. Returns (decision, merged_name)."""
    x1 = max(0, int(box[0]) - 12)
    y1 = max(0, int(box[1]) - 12)
    x2 = min(image.width, int(box[2]) + 12)
    y2 = min(image.height, int(box[3]) + 12)
    crop = image.crop((x1, y1, x2, y2))
    content = [
        {"type": "text", "text": _VLM_PROMPT.format(a=name_a, b=name_b)},
        {"type": "image_url", "image_url": {"url": _pil_to_data_url(crop)}},
    ]
    r = provider.send([{"role": "user", "content": content}], None)
    text = (r["choices"][0]["message"].get("content") or "").strip()
    low = text.lower()
    if low.startswith("separate"):
        return "separate", None
    if low.startswith("same"):
        if "|" in text:
            name = text.split("|", 1)[1].strip()
        else:
            name = text[4:].strip().lstrip(":- ").strip()
        return "same", (name or f"{name_a}+{name_b}")
    # unrecognized reply: keep the pair separate rather than merge on a guess
    return "separate", None


def _unique_key(masks, base, exclude=()):
    key = base
    k = 2
    while key in masks or key in exclude:
        key = f"{base}_{k}"
        k += 1
    return key


def resolve_overlaps(state, provider):
    """Detect + VLM-verify + merge overlapping same-object masks (idempotent per state).

    Mutates ``state.masks`` / ``state.boxes`` in place and records redirects in
    ``state.mask_redirect`` so ``backproject_obb`` can still resolve old names.
    Returns a human-readable summary (empty string if nothing to merge).
    """
    if getattr(state, "_overlaps_resolved", False):
        return getattr(state, "_overlaps_summary", "")

    state._overlaps_resolved = True
    summary_lines = []
    skip = set()

    while True:
        pair = None
        for a, b, cont in find_overlapping_pairs(state.masks):
            if frozenset((a, b)) not in skip:
                pair = (a, b, cont)
                break
        if pair is None:
            break

        a, b, cont = pair
        try:
            image = state.load_image()
            decision, merged = _vlm_check(
                provider, image, a, b, union_box(state.boxes[a], state.boxes[b])
            )
        except Exception as e:
            skip.add(frozenset((a, b)))
            summary_lines.append(
                f"[resolve_overlaps] VLM check failed for '{a}'+'{b}' ({e}); kept separate"
            )
            continue

        if decision == "same" and merged:
            merged = _unique_key(state.masks, merged, exclude=(a, b))
            state.masks[merged] = state.masks[a] | state.masks[b]
            state.boxes[merged] = union_box(state.boxes[a], state.boxes[b])
            for old in (a, b):
                state.mask_redirect[old] = merged
                state.masks.pop(old, None)
                state.boxes.pop(old, None)
            # fold forward any earlier redirects that pointed at the now-merged names
            for k, v in list(state.mask_redirect.items()):
                if v in (a, b) and k not in (a, b):
                    state.mask_redirect[k] = merged
            summary_lines.append(f"merged '{a}' + '{b}' -> '{merged}' (containment={cont:.3f})")
        else:
            skip.add(frozenset((a, b)))
            summary_lines.append(
                f"kept separate: '{a}' + '{b}' (containment={cont:.3f}, VLM says separate)"
            )

    summary = "\n".join(summary_lines)
    state._overlaps_summary = summary
    return summary


class ResolveOverlapsTool:
    """LLM tool: run the overlap detection + VLM verification + merge step."""

    def __init__(self, state, provider):
        self.state = state
        self.provider = provider

    def definition(self):
        return {
            "name": "resolve_overlaps",
            "description": (
                "Detect SAM3 masks where one is mostly contained in the other "
                f"(containment = intersection / min area, >= {OVERLAP_CONTAINMENT_THRESHOLD:.2f}) "
                "and, via a VLM check, merge those that are actually the same physical object "
                "or parts of one object. Returns which masks were merged (or 'no overlapping "
                "masks to merge'). Run this after sam3_segment and before backproject_obb; "
                "backproject_obb also runs it automatically on its first call."
            ),
            "parameters": {"type": "object", "properties": {}},
        }

    def execute(self, args):
        try:
            summary = resolve_overlaps(self.state, self.provider)
        except Exception as e:
            return "Error: resolve_overlaps failed: " + str(e)
        if not summary:
            return "[resolve_overlaps] no overlapping masks to merge."
        return "[resolve_overlaps]\n" + summary

"""``write_perception_state`` tool: persist the shared :class:`PerceptionState` to disk.

The ``PerceptionState`` caches large in-process objects — the input PIL image, the
DA3 :class:`Reconstruction` (depth / intrinsics / extrinsics / conf), and every SAM3
bool mask / box — that cannot round-trip through the LLM's JSON tool protocol. This
module serializes them to a directory so a later run (or BaseAgent, via
``--state-save-path``) can reload them without re-running SAM3/DA3.

On-disk layout (every piece is optional and omitted from the manifest when absent)::

    <out_dir>/
        image.png            RGB input image (if loaded)
        reconstruction.npz   depth/intrinsics/extrinsics/conf/width/height (if DA3 ran)
        masks/<name>.npy     one bool (H, W) array per cached SAM3 mask
        boxes.json           name -> [x1, y1, x2, y2] (original-resolution xyxy)
        manifest.json        summary of everything written above
"""

import json
import re
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _jsonify(obj):
    """Convert numpy scalars/arrays into plain JSON types."""
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def _safe_name(name):
    s = re.sub(r"[^0-9a-zA-Z_-]+", "_", str(name)).strip("_")
    return s or "mask"


def save_perception_state(state, out_dir):
    """Serialize ``state`` (a ``PerceptionState``) into ``out_dir`` and return the manifest dict.

    Never raises for an empty state: an unpopulated state just yields a manifest with
    ``image_path``/``out_dir`` and no artifact entries.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "image_path": state.image_path,
        "out_dir": str(out.resolve()),
    }

    # image (only if it was actually loaded)
    if getattr(state, "image", None) is not None:
        img = out / "image.png"
        state.image.save(img)
        manifest["image"] = img.name

    # DA3 reconstruction
    rec = getattr(state, "reconstruction", None)
    if rec is not None:
        arrs = {
            "depth": np.asarray(rec.depth),
            "intrinsics": np.asarray(rec.intrinsics),
            "extrinsics": np.asarray(rec.extrinsics),
            "width": np.asarray(rec.width),
            "height": np.asarray(rec.height),
        }
        if getattr(rec, "conf", None) is not None:
            arrs["conf"] = np.asarray(rec.conf)
        rec_path = out / "reconstruction.npz"
        np.savez_compressed(rec_path, **arrs)
        manifest["reconstruction"] = rec_path.name

    # SAM3 masks (bool (H, W) ndarrays)
    masks = getattr(state, "masks", {}) or {}
    if masks:
        masks_dir = out / "masks"
        masks_dir.mkdir(parents=True, exist_ok=True)
        mask_files = {}
        used = set()
        for name, mask in masks.items():
            base = _safe_name(name)
            fname = base
            k = 0
            while fname in used:
                k += 1
                fname = f"{base}_{k}"
            used.add(fname)
            p = masks_dir / f"{fname}.npy"
            np.save(p, np.asarray(mask, dtype=bool))
            mask_files[name] = str(p.relative_to(out))
        manifest["masks"] = mask_files

    # SAM3 boxes (name -> [x1, y1, x2, y2])
    boxes = getattr(state, "boxes", {}) or {}
    if boxes:
        boxes_path = out / "boxes.json"
        boxes_path.write_text(
            json.dumps(_jsonify(boxes), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest["boxes"] = boxes_path.name

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


class WritePerceptionStateTool:
    """LLM tool: save the shared perception state to disk.

    Follows the ex-articraft tool_layer convention: ``definition()`` returns an
    OpenAI function schema and ``execute(args)`` takes a JSON string.
    """

    def __init__(self, state, default_out_dir=None):
        self.state = state
        self.default_out_dir = default_out_dir

    def definition(self):
        return {
            "name": "write_perception_state",
            "description": (
                "Save the current perception state to disk: the input image (image.png), the "
                "DA3 reconstruction (reconstruction.npz with depth/intrinsics/extrinsics/conf/"
                "width/height), every cached SAM3 mask (masks/<name>.npy, bool HxW) and every "
                "box (boxes.json, name -> [x1,y1,x2,y2]). Run `sam3_segment` / `da3_reconstruct` "
                "first to populate the state; a still-empty field is simply omitted. Returns a "
                "JSON manifest of the saved files (including the absolute out_dir)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "out_dir": {
                        "type": "string",
                        "description": (
                            "Directory to write into. Defaults to <repo>/perception_out/<timestamp>."
                        ),
                    },
                },
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args or "{}")
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        out_dir = params.get("out_dir") or self.default_out_dir
        if not out_dir:
            out_dir = _REPO_ROOT / "perception_out" / time.strftime("%Y%m%d_%H%M%S")
        try:
            manifest = save_perception_state(self.state, out_dir)
        except Exception as e:
            return "Error: write_perception_state failed: " + str(e)
        return json.dumps(manifest, ensure_ascii=False, indent=2)

"""compile tool: run the room.py the LLM wrote and validate it, forming the write-compile-fix loop.

room.py convention (either one):
1. define ``build_scene_graph()`` returning a scene-graph dict (``{"nodes": [...], "edges": [...]}``);
2. define a module-level variable ``scene`` (or ``graph``).

Validation calls ``sdk.validation.validate_scene_graph`` (structure/collision/floating); when both a DA3 reconstruction and SAM3 boxes are available, it additionally calls ``validate_image_reprojection`` for an image-consistency check, reporting each object's deviation from its SAM3 box after reprojection (small deviation ok, otherwise warning).
"""

import importlib.util
import json
import os
import traceback

from sdk.validation import validate_scene_graph, validate_image_reprojection


def load_scene_graph(path):
    """Execute room.py and extract the scene graph. Returns (graph, error)."""
    path = os.path.abspath(path)
    spec = importlib.util.spec_from_file_location("_layoutagent_layout", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        return None, f"Error executing room.py: {e}\n{traceback.format_exc()}"

    for attr in ("build_scene_graph",):
        if hasattr(module, attr):
            fn = getattr(module, attr)
            if callable(fn):
                try:
                    return fn(), None
                except Exception as e:
                    return None, f"Error calling build_scene_graph(): {e}\n{traceback.format_exc()}"

    for attr in ("scene", "graph"):
        if hasattr(module, attr):
            return getattr(module, attr), None

    return None, "room.py must define build_scene_graph() or a scene/graph variable"


def compile_layout(path, floor_tolerance=0.05, reconstruction=None, boxes=None,
                   image_size=None, iou_threshold=0.5):
    """Execute room.py and validate it. Returns ``(graph, failures, warnings, notes)``.

    On execution failure graph=None and failures holds the error message. If reconstruction + boxes are provided, an image reprojection consistency check is appended (each object's deviation from its SAM3 box).
    """
    graph, error = load_scene_graph(path)
    if error:
        return None, [error], [], []
    failures, warnings, notes = validate_scene_graph(graph, floor_tolerance)

    if reconstruction is not None and boxes:
        rw, rn = validate_image_reprojection(
            graph, reconstruction, boxes, image_size=image_size,
            iou_threshold=iou_threshold,
        )
        warnings.extend(rw)
        notes.extend(rn)

    return graph, failures, warnings, notes


def format_diagnostics(failures, warnings, notes):
    """Assemble the three tiers of diagnostics into readable feedback for the LLM."""
    lines = []
    if failures:
        lines.append(f"[failure] {len(failures)}, must fix:")
        lines += [f"  - {f}" for f in failures]
    if warnings:
        lines.append(f"[warning] {len(warnings)}, should fix:")
        lines += [f"  - {w}" for w in warnings]
    if notes:
        lines.append(f"[note] {len(notes)}:")
        lines += [f"  - {n}" for n in notes]
    if not (failures or warnings or notes):
        lines.append("[ok] validation passed, no failure/warning/note.")
    return "\n".join(lines)


class CompileTool:
    """LLM tool: run room.py and return three-tier diagnostics (failure/warning/note).

    When a shared ``state`` (PerceptionState) is passed and it already has a DA3 reconstruction + SAM3 boxes, an additional image reprojection consistency check is performed.
    """

    def __init__(self, path="room.py", state=None):
        self.path = path
        self.state = state

    def definition(self):
        return {
            "name": "compile",
            "description": (
                "Run the layout script (room.py) and validate the scene graph it produces. "
                "Returns diagnostics with three tiers: failure, warning, note. If perception "
                "(DA3 reconstruction + SAM3 boxes) is available, also reprojects each object OBB "
                "into image space and reports its deviation from the SAM3 box."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the layout script (default room.py)",
                    },
                },
                "required": [],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args)
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        path = params.get("path") or self.path
        reconstruction = None
        boxes = None
        image_size = None
        if self.state is not None:
            reconstruction = getattr(self.state, "reconstruction", None)
            boxes = getattr(self.state, "boxes", None)
            image = getattr(self.state, "image", None)
            if image is not None:
                image_size = image.size  # (W, H)
        _, failures, warnings, notes = compile_layout(
            path,
            reconstruction=reconstruction,
            boxes=boxes,
            image_size=image_size,
        )
        return format_diagnostics(failures, warnings, notes)

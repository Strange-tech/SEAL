"""materialize / export_obj tool: materialize room.py's scene graph into OBBs and export an OBJ.

Corresponds to plan.md's "land the scene graph as viewable geometry". The core logic lives in ``sdk.scene`` (``materialize_obbs`` + ``obbs_to_obj``); this file just wraps it as an LLM-callable tool.
"""

import json
import os

from sdk.scene import materialize_obbs, obbs_to_obj
from tools.compile import load_scene_graph


def export_scene_graph(path, out=None):
    """Materialize a layout script's scene graph to OBJ.

    Returns ``(ok, message)``: on failure ``ok`` is False and ``message`` is a
    human-readable error; on success ``ok`` is True and ``message`` is the write
    summary.
    """
    graph, error = load_scene_graph(path)
    if error:
        return False, "Error: " + error
    obbs = materialize_obbs(graph)
    if not obbs:
        return False, "Error: scene graph has no nodes to export"
    out = out or (os.path.splitext(path)[0] + ".obj")
    try:
        written = obbs_to_obj(obbs, out)
    except Exception as e:
        return False, "Error: OBJ export failed: " + str(e)
    summary = ", ".join(f"{o['id']}({o['type']})" for o in obbs)
    return True, f"wrote {len(obbs)} OBB(s) -> {written}\n  {summary}"


class ExportObjTool:
    """LLM tool: materialize the scene graph into OBBs and export an OBJ file for viewing."""

    def __init__(self, path="room.py"):
        self.path = path

    def definition(self):
        return {
            "name": "export_obj",
            "description": (
                "Materialize the layout script's scene graph into OBB boxes and export them as a "
                "Wavefront OBJ file for visualization. Returns the output path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the layout script (default room.py)",
                    },
                    "out": {
                        "type": "string",
                        "description": "Output OBJ path (default <layout script stem>.obj)",
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
        ok, message = export_scene_graph(path, out=params.get("out"))
        if not ok:
            return message
        return f"[export_obj] {message}"

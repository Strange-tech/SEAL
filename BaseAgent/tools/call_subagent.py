"""Expose the cross-project orchestrators (subprocess_agent) as BaseAgent tools.

Registered in BaseAgent's default tool set (see main.py), letting the orchestrating LLM
call LayoutAgent / ArtiAgent directly. Each call spawns a slow, GPU-heavy subprocess.
"""

import json

from subprocess_agent import run_layout_agent, run_arti_agent, orchestrate_reconstruct


# The image path attached to the current turn. main.py sets this before each agent.run
# so the delegation tools can forward the image even if the LLM omits image_path.
_current_image_path: str | None = None


def set_current_image(path: str | None) -> None:
    global _current_image_path
    _current_image_path = path


class CallLayoutAgentTool:
    def definition(self):
        return {
            "name": "call_layout_agent",
            "description": (
                "Delegate WHOLE-IMAGE segmentation or room reconstruction to LayoutAgent only. "
                "LayoutAgent returns the scene graph (nodes/edges; every object node carries its box "
                "C=center, D=dims, theta=orientation) and, when state_save_path is given, saves the raw "
                "perception state (SAM3 masks/boxes, DA3 reconstruction) to that directory (manifest in "
                "result.perception). This tool does NOT generate per-object 3D assets — use call_arti_agent "
                "or reconstruct_scene for that. Pass the full room/layout description (include every object and layout detail; do not truncate). Forward the attached image's exact path via "
                "image_path. Trust the returned result — do not re-verify it with bash."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Room/layout description for LayoutAgent (include every object and layout detail; do not truncate)."},
                    "image_path": {"type": "string", "description": "Exact path of the attached image (forward it when present)."},
                    "state_save_path": {"type": "string", "description": "Optional directory to save the perception state (image, reconstruction, masks, boxes)."},
                },
                "required": ["task"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args) or {}
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        task = (params.get("task") or "").strip()
        if not task:
            return "Error: task is required"
        try:
            out = run_layout_agent(
                task,
                image_path=params.get("image_path") or _current_image_path,
                state_save_path=params.get("state_save_path"),
            )
        except Exception as e:
            return "Error: LayoutAgent delegation failed: " + str(e)
        return json.dumps(out, ensure_ascii=False, indent=2)


class CallArtiAgentTool:
    def definition(self):
        return {
            "name": "call_arti_agent",
            "description": (
                "Delegate a SINGLE named object's articulated asset (URDF + mesh) to ArtiAgent only. "
                "This tool does NOT do whole-image segmentation or room layout — use call_layout_agent "
                "or reconstruct_scene for that. Pass the object description (do not truncate it). Forward the object's reference image — a mask image "
                "(the object isolated by its SAM3 mask, transparent background) is ideal so ArtiAgent cannot "
                "re-segment neighbours — via image_path. Optionally pass box to constrain the object's "
                "scale and position. Returns {ok, output, result} where result is {asset_dir, swept_bbox} "
                "written to BaseAgent/output/artiagent/. Trust the returned result — do not re-verify or "
                "re-render it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Object description for ArtiAgent (do not truncate)."},
                    "image_path": {"type": "string", "description": "Exact path of the object's reference image (a tight crop is ideal)."},
                    "box": {"type": "string", "description": "Optional JSON {\"center\":[cx,cy,cz],\"dims\":[w,h,l],\"rpy\":[rx,ry,rz]} constraining the object's scale/position (y-up, +z forward). rpy is in RADIANS."},
                },
                "required": ["task"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args) or {}
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        task = (params.get("task") or "").strip()
        if not task:
            return "Error: task is required"
        box = params.get("box")
        if isinstance(box, str) and box.strip():
            try:
                box = json.loads(box)
            except json.JSONDecodeError:
                return "Error: box must be a JSON object {center, dims, rpy}"
        if not isinstance(box, dict):
            box = None
        try:
            out = run_arti_agent(
                task,
                image_path=params.get("image_path") or _current_image_path,
                box=box,
            )
        except Exception as e:
            return "Error: ArtiAgent delegation failed: " + str(e)
        return json.dumps(out, ensure_ascii=False, indent=2)


class ReconstructSceneTool:
    def definition(self):
        return {
            "name": "reconstruct_scene",
            "description": (
                "Run the END-TO-END SEAL pipeline: LayoutAgent first (whole-image segmentation + room "
                "reconstruction + save perception state), then for every object in the returned scene graph, "
                "generate a per-object articulated asset with ArtiAgent IN PARALLEL. Each object is isolated "
                "by its SAM3 mask — ArtiAgent receives that object's mask image (transparent background) and "
                "its text label, constrained to the object's box (part-nodes like sofa base/back/arm are "
                "grouped back into one object). Use this when the user wants a full scene turned into both a "
                "layout and 3D assets. Returns {ok, layout, perception, objects} where objects maps each "
                "object id to {asset_dir, center, dims, rpy} — rpy in RADIANS (converted from the scene graph's theta in degrees). Pass image_path when an image is attached; omit it for text-only reconstruction."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Scene description — include every object and layout detail; do not truncate."},
                    "image_path": {"type": "string", "description": "Exact path of the attached image (forward it when present)."},
                },
                "required": ["task"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args) or {}
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        task = (params.get("task") or "").strip()
        if not task:
            return "Error: task is required"
        image = params.get("image_path") or _current_image_path
        try:
            out = orchestrate_reconstruct(image, task)
        except Exception as e:
            return "Error: reconstruct_scene failed: " + str(e)
        return json.dumps(out, ensure_ascii=False, indent=2)

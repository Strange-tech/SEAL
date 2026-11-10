"""Expose the cross-project orchestrators (subprocess_agent) as BaseAgent tools.

Registered in BaseAgent's default tool set (see main.py), letting the orchestrating LLM
call LayoutAgent / ArtiAgent directly. Each call spawns a slow, GPU-heavy subprocess.
"""

import json

from subprocess_agent import run_layout_agent, run_arti_agent


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
                "Delegate whole-image segmentation or room reconstruction to LayoutAgent (SAM3 "
                "segmentation + DA3 depth). Pass a SHORT task — a few words, at most 8; "
                "LayoutAgent's structurer expands a terse prompt from the image, and long tasks "
                "skip it and degrade quality. If the user attached an image, forward its exact path "
                "via image_path so the sub-agent sees it. Returns {ok, output, result} where result is "
                "the scene graph (nodes/edges) written to BaseAgent/output/layoutagent/. Trust the "
                "returned result — do not re-verify it with bash."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Short reconstruction instruction (<=8 words) for LayoutAgent."},
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
        try:
            out = run_layout_agent(
                task,
                image_path=params.get("image_path") or _current_image_path,
            )
        except Exception as e:
            return "Error: LayoutAgent delegation failed: " + str(e)
        return json.dumps(out, ensure_ascii=False, indent=2)


class CallArtiAgentTool:
    def definition(self):
        return {
            "name": "call_arti_agent",
            "description": (
                "Delegate a single object's asset generation to ArtiAgent. Pass a SHORT task — a "
                "few words, at most 8; ArtiAgent's structurer expands it from the image, and long "
                "tasks skip it and degrade quality. If the user attached an image, forward its exact "
                "path via image_path so the sub-agent sees it. Returns {ok, output, result} where result is "
                "{asset_dir, real_bbox} written to BaseAgent/output/artiagent/. Trust the returned "
                "result — do not re-verify or re-render it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Short object description (<=8 words) for ArtiAgent."},
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
        try:
            out = run_arti_agent(
                task,
                image_path=params.get("image_path") or _current_image_path,
            )
        except Exception as e:
            return "Error: ArtiAgent delegation failed: " + str(e)
        return json.dumps(out, ensure_ascii=False, indent=2)

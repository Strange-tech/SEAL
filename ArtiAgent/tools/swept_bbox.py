import json
from pathlib import Path
from agent.bbox import compute_model_swept_bbox
from basic_tools import WORK_DIR

class SweptBboxTool:
	def definition(self):
		return {
			"name": "swept_bbox",
			"description": (
				"Compute the swept (joint-range) bounding box of the current model.py: the "
				"axis-aligned box that contains every part's geometry across the full range of "
				"each joint's motion (the swept volume). Returns {center:[cx,cy,cz], dims:[w,h,l]} "
				"in the y-up / +z-forward world frame. Use it to verify the object fits the "
				"--box constraint, or to report the true footprint back to the layout engine."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"samples": {"type": "integer", "description": "Cap on pose combinations to sample (optional; default enumerates the full joint-range product)"},
				},
			},
		}

	def execute(self, args):
		try:
			params = json.loads(args)
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		samples = params.get("samples")
		if samples is not None:
			samples = int(samples)
		try:
			center, dims = compute_model_swept_bbox(
				Path(WORK_DIR) / "model.py",
				asset_root=Path(WORK_DIR) / ".bbox_tmp",
				samples=samples,
			)
		except Exception as e:
			return "Error: swept_bbox failed: " + str(e)
		return json.dumps(
			{"center": [round(float(v), 6) for v in center], "dims": [round(float(v), 6) for v in dims]},
			indent=2,
		)



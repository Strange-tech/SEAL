import json
from pathlib import Path
from agent.compiler import compile_urdf_report_maybe_timeout
from agent.feedback import render_compile_signals, compile_signal_bundle_from_exception
from agent.bbox import compute_model_real_bbox
from basic_tools import WORK_DIR

class CompileModelTool:
	def __init__(self, box=None):
		self.box = box

	def definition(self):
		return {
			"name": "compile_model",
			"description": (
				"Run full model compile and QC on the current model.py. "
				"Use this after one or more edits when you want full compile/test feedback. "
				"The harness automatically runs baseline sanity/QC checks for model validity, exactly one root part, mesh assets, floating disconnected part groups, disconnected geometry islands inside a part, and current-pose real 3D overlaps. "
				"Do not manually author that baseline stack in run_tests(); reserve run_tests() for exact checks, targeted poses, and explicit allowances. "
				"The tool returns the same structured <compile_signals> block used by the harness for clean success, warnings, or failures. When a --box constraint is set, the result also includes a <box_delta> report comparing the layout box to the object's actual measured box."
			),
			"parameters": {
				"type": "object",
				"properties": {},
				"required": [],
			},
		}

	def execute(self, args):
		try:
			json.loads(args)
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		model_path = Path(WORK_DIR) / "model.py"
		try:
			report = compile_urdf_report_maybe_timeout(
				model_path,
				sdk_package="sdk",
				rewrite_visual_glb=False,
				asset_root=Path(WORK_DIR) / ".compile_tmp",
			)
			out = render_compile_signals(report.signal_bundle)
		except Exception as e:
			out = render_compile_signals(compile_signal_bundle_from_exception(e))
		if self.box is not None:
			out += chr(10) + chr(10) + self._box_delta_text()
		return out

	def _box_delta_text(self):
		try:
			center, dims = compute_model_real_bbox(
				Path(WORK_DIR) / "model.py",
				asset_root=Path(WORK_DIR) / ".bbox_tmp",
			)
		except Exception as e:
			return "<box_delta>" + chr(10) + "(actual box not computable: " + str(e) + ")" + chr(10) + "</box_delta>"
		tc = self.box["center"]
		td = self.box["dims"]
		tr = self.box["rpy"]
		pos = [round(tc[i] - center[i], 4) for i in range(3)]
		scale = [round(td[i] / dims[i], 4) if dims[i] else None for i in range(3)]
		rot = [round(tr[i], 4) for i in range(3)]
		return chr(10).join([
			"<box_delta>",
			"target box (from layout --box): center=" + str(tc) + " dims=" + str(td) + " rpy=" + str(tr),
			"actual box (measured):         center=" + str([round(v, 4) for v in center]) + " dims=" + str([round(v, 4) for v in dims]),
			"position delta (target - actual): " + str(pos),
			"scale delta (target / actual): " + str(scale),
			"rotation delta (target rpy, object authored at rpy=[0,0,0]): " + str(rot),
			"Placement note: position/rotation deltas are the scene placement, applied separately by the renderer (the object stays at the origin). Judge only the SIZE: is the actual dims acceptable for the requested object? If yes, conclude; if not, adjust the model size and recompile.",
			"</box_delta>",
		])


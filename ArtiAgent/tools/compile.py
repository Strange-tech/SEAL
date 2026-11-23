import json
from pathlib import Path
from agent.compiler import compile_urdf_report_maybe_timeout
from agent.feedback import render_compile_signals, compile_signal_bundle_from_exception
from agent.bbox import compute_model_real_bbox, compute_zero_pose_bbox
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
		box_delta = chr(10).join([
			"<box_delta>",
			"target box (from layout --box): center=" + str(tc) + " dims=" + str(td) + " rpy=" + str(tr),
			"actual box (measured):         center=" + str([round(v, 4) for v in center]) + " dims=" + str([round(v, 4) for v in dims]),
			"position delta (target - actual): " + str(pos),
			"scale delta (target / actual): " + str(scale),
			"rotation delta (target rpy, object authored at rpy=[0,0,0]): " + str(rot),
			"Placement note: position/rotation deltas are the scene placement, applied separately by the renderer (the object stays at the origin). Check <orientation_check> first to rule out a wrong axis (lying down / rotated), then judge the SIZE: are the actual dims acceptable for the requested object?",
			"</box_delta>",
		])
		return box_delta + chr(10) + chr(10) + self._orientation_check_text()

	def _orientation_check_text(self):
		try:
			_, zd = compute_zero_pose_bbox(
				Path(WORK_DIR) / "model.py",
				asset_root=Path(WORK_DIR) / ".bbox_tmp",
			)
		except Exception as e:
			return "<orientation_check>" + chr(10) + "(zero-pose bbox not computable: " + str(e) + ")" + chr(10) + "</orientation_check>"
		T = self.box["dims"]
		A = [zd[0], zd[1], zd[2]]
		perms = [
			((0, 1, 2), "identity"),
			((0, 2, 1), "height(y) and depth(z) appear swapped -> rotate 90 deg about X"),
			((1, 0, 2), "width(x) and height(y) appear swapped -> rotate 90 deg about Z"),
			((2, 1, 0), "width(x) and depth(z) appear swapped -> rotate 90 deg about Y"),
			((1, 2, 0), "axes cyclically permuted x->y->z (uncommon)"),
			((2, 0, 1), "axes cyclically permuted z->y->x (uncommon)"),
		]
		def rel_err(p):
			return sum(abs(p[i] - T[i]) / max(abs(T[i]), 1e-6) for i in range(3))
		best_idx, best_label = min(perms, key=lambda pr: rel_err([A[i] for i in pr[0]]))
		best_score = rel_err([A[i] for i in best_idx])
		id_score = rel_err(A)
		lines = [
			"<orientation_check>",
			"target box dims (w,h,d): " + str([round(v, 4) for v in T]),
			"zero-pose dims (w,h,d):  " + str([round(v, 4) for v in A]),
			"best axis alignment: " + best_label + "  (rel. fit error %.3f vs identity %.3f)" % (best_score, id_score),
		]
		if best_label == "identity" or best_score >= 0.7 * id_score:
			lines.append("verdict: orientation OK — any mismatch is a SIZE issue, not orientation.")
		else:
			lines.append("if re-oriented, dims would be: " + str([round(A[i], 4) for i in best_idx]))
			lines.append("verdict: SUSPECTED ORIENTATION ERROR — " + best_label + ".")
			lines.append("Fix by RE-AUTHORING the model in the canonical y-up frame (x=width, y=up/height, z=front/depth); do NOT add an rpy rotation to the placement.")
		lines.append("</orientation_check>")
		return chr(10).join(lines)


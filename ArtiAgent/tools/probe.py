import json
from pathlib import Path
from agent.probe_layer import run_probe
from basic_tools import WORK_DIR

class ProbeModelTool:
	def definition(self):
		return {
			"name": "probe_model",
			"description": (
				"""
				Execute a short Python snippet against the current bound `model.py` for inspection-only geometry diagnosis.

				This tool is intended for inspection-only use on the current model file.
				Use it when placements, clearances, containment, overlap risk, or pose behavior are uncertain.

				Execution contract:
				- Write ordinary Python code.
				- Use this tool only for non-mutating inspection and measurement.
				- `emit(value)` must be called exactly once.
				- `value` must be JSON-serializable.
				- `print(...)` is allowed for debugging only. It is captured separately and returned only when requested.
				- Do not write files, modify `object_model`, launch subprocesses, access the network, or perform destructive actions.
				- The snippet runs in an isolated subprocess with a timeout.

				Guidance:
				- Read `docs/sdk/references/probe-tooling.md` for the exact probe helper catalog and signatures.
				- `probe_model` is especially useful when an overlap, floating/support, containment, or exact-pair issue is ambiguous, or when a first geometry repair did not clarify the problem.
				- IMPORTANT: Do not import probe helpers from `sdk` or other modules inside the snippet. Helpers such as `part(...)`, `joint(...)`, `visual(...)`, `pose(...)`, `emit(...)`, `pair_report(...)`, and related review helpers are already injected into the snippet namespace.
				- The helper surface includes lookup, measurement, relationship, and review helpers such as `part(...)`, `visual(...)`, `pose(...)`, `summary(...)`, `pair_report(...)`, `find_clearance_risks(...)`, and `geometry_connectivity_report(...)`.
				- Except for the explicit `aabb(...)` helper, probe measurements should prefer exact geometry over transformed AABB approximations.
				- These helpers are tool-local review conveniences built on the current `object_model` and `TestContext`.
				- They are not part of the public SDK API and may use internal exact-geometry helpers.
				- Use `geometry_connectivity_report(...)` when a part visually appears to contain floating mesh islands and you need to compare raw mesh components against what the current connectivity QC can see.
				"""
			),
			"parameters": {
				"type": "object",
				"properties": {
					"code": {"type": "string", "description": "Python snippet to run; call emit(value) exactly once"},
					"timeout_ms": {"type": "integer", "description": "Timeout in milliseconds, optional (default 600000)"},
					"include_stdout": {"type": "boolean", "description": "Capture snippet stdout/stderr, optional (default false)"},
				},
				"required": ["code"],
			},
		}

	def execute(self, args):
		try:
			params = json.loads(args)
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		code = params.get("code", "") or ""
		if not code.strip():
			return "Error: code cannot be empty"
		timeout_ms = params.get("timeout_ms") or 600000
		if int(timeout_ms) < 100:
			return "Error: timeout_ms must be >= 100"
		include_stdout = bool(params.get("include_stdout", False))
		try:
			result = run_probe(
				Path(WORK_DIR) / "model.py",
				code,
				timeout_ms=int(timeout_ms),
			)
		except Exception as e:
			return "Error: probe failed: " + str(e)
		if not result.get("ok"):
			err = result.get("error") or {}
			etype = err.get("type", "unknown_error")
			msg = err.get("message", "")
			tb = err.get("traceback", "")
			lines = [f"Probe error [{etype}]: {msg}"]
			if tb:
				lines.append("")
				lines.append(tb)
			if include_stdout:
				if result.get("stdout"):
					lines.append("--- stdout ---\n" + result["stdout"])
				if result.get("stderr"):
					lines.append("--- stderr ---\n" + result["stderr"])
			return "\n".join(lines)
		parts = [json.dumps(result.get("result"), indent=2, default=str)]
		if include_stdout:
			if result.get("stdout"):
				parts.append("--- stdout ---\n" + result["stdout"])
			if result.get("stderr"):
				parts.append("--- stderr ---\n" + result["stderr"])
		return "\n".join(parts)



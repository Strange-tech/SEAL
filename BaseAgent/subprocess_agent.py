"""Cross-project subprocess orchestration.

Wraps LayoutAgent and ArtiAgent — two separate agent projects — as subprocesses.
BaseAgent (the long-running orchestrator) calls these to delegate scene layout
(LayoutAgent) and per-object geometry (ArtiAgent), exchanging machine-readable
JSON rather than sharing an in-process import.

Each project keeps its own system prompt / SDK / session / files, which maps
naturally onto a subprocess: the CLI arguments carry the task in, and a JSON
emit-file carries the structured result out.

Interpreter / project paths are overridable via environment variables so the
orchestrator does not hardcode one machine's layout:

  LAYOUT_PYTHON / LAYOUT_AGENT_DIR
  ARTI_PYTHON   / ARTI_AGENT_DIR
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


# Known-good interpreter for LayoutAgent (SAM3/DA3 live in the `layout` conda env).
LAYOUT_PYTHON = _env("LAYOUT_PYTHON", "/home/data/johnli/miniconda3/envs/layout/bin/python")
LAYOUT_AGENT_DIR = Path(_env("LAYOUT_AGENT_DIR", str(Path(__file__).resolve().parent.parent / "LayoutAgent")))

# ArtiAgent now runs in the same `layout` env (Python 3.10): cadquery 2.7.0 / manifold3d /
# python-fcl / trimesh / networkx / zstandard are installed there (numpy 2.2.6). Its
# Windows-only .venv is unused on Linux; override ARTI_PYTHON to point elsewhere if needed.
ARTI_PYTHON = _env("ARTI_PYTHON", "/home/data/johnli/miniconda3/envs/layout/bin/python")
ARTI_AGENT_DIR = Path(_env("ARTI_AGENT_DIR", str(Path(__file__).resolve().parent.parent / "ArtiAgent")))
BASE_ROOT = Path(__file__).resolve().parent  # BaseAgent directory; delegated output lands under output/

DEFAULT_TIMEOUT = 1200  # seconds; layout (SAM3+DA3) and arti (cadquery) can be slow
_MAX_TEE_LINES = 20000  # per-stream cap on sub-agent output buffered back to the LLM


class SubprocessError(RuntimeError):
    """Raised when a delegated project subprocess cannot be launched or times out."""


def _run(project_dir: Path, python: str, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    # `-u` forces the child to unbuffered stdio so its prints reach us line-by-line
    # instead of sitting in an 8KB block buffer until the process exits.
    cmd = [python, "-u", str(project_dir / "main.py"), *args]
    name = project_dir.name
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as e:
        raise SubprocessError(
            f"Failed to launch {name} (interpreter {python!r}): {e}"
        ) from e

    # Announce the launch immediately so the user knows a slow subprocess started.
    sys.stderr.write(f"[{name}] launching: {' '.join(cmd)}\n")
    sys.stderr.flush()

    def _pump(pipe, buf, label):
        # Stream each line to BaseAgent's own terminal (stderr) as it arrives, and tee
        # the same lines into a bounded buffer that still gets reported to the LLM.
        try:
            for line in iter(pipe.readline, ""):
                if not line:
                    break
                buf.append(line)
                if len(buf) > _MAX_TEE_LINES:
                    del buf[:_MAX_TEE_LINES // 2]
                sys.stderr.write(f"[{label}] {line}")
                sys.stderr.flush()
        finally:
            pipe.close()

    out_buf: list[str] = []
    err_buf: list[str] = []
    t_out = threading.Thread(target=_pump, args=(proc.stdout, out_buf, name), daemon=True)
    t_err = threading.Thread(target=_pump, args=(proc.stderr, err_buf, name), daemon=True)
    t_out.start()
    t_err.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        t_out.join()
        t_err.join()
        raise SubprocessError(
            f"{name} timed out after {timeout}s: {' '.join(cmd)}"
        ) from None

    t_out.join()
    t_err.join()

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode,
        stdout="".join(out_buf),
        stderr="".join(err_buf),
    )


def _read_json(path: str | None) -> Any:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _slug(text: str) -> str:
    """Turn a task into a short filesystem-safe name for the output filename."""
    s = re.sub(r"[^0-9a-zA-Z]+", "-", (text or "").lower()).strip("-")
    return s[:48] or "run"


def _default_output(agent_name: str, task: str) -> Path:
    """Result JSON lives under BaseAgent/output/<agent>/, not the sub-agent's own tree."""
    out = BASE_ROOT / "output" / agent_name
    out.mkdir(parents=True, exist_ok=True)
    return out / f"{_slug(task)}.json"


def _delegation_result(name: str, proc: subprocess.CompletedProcess, out_path: Path, payload: Any = None) -> dict:
    """Authoritative result handed back to the orchestrating LLM.

    On success this is a clean {agent, ok, output, result} with no stdout/stderr noise, so
    the orchestrator trusts it instead of re-verifying the sub-agent's work with bash.
    """
    if proc.returncode == 0 and payload is not None:
        return {"agent": name, "ok": True, "output": str(out_path), "result": payload}
    return {
        "agent": name,
        "ok": False,
        "returncode": proc.returncode,
        "output": str(out_path),
        "result": payload,
        "error": (proc.stderr or "").strip()[-1500:],
    }


def run_layout_agent(
    task: str,
    *,
    image_path: str | None = None,
    emit_scene_graph: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Delegate scene layout to LayoutAgent and return its emitted scene graph.

    The scene graph (nodes/edges) is always written to BaseAgent/output/layoutagent/ and
    returned in `result`; `emit_scene_graph` overrides that location if given.
    """
    nwords = len((task or "").split())
    if nwords > 8:
        print(f"[LayoutAgent] warning: task is {nwords} words — a terse (<=8 word) task "
              f"lets the structurer expand it and works better", file=sys.stderr)
    out_path = Path(emit_scene_graph) if emit_scene_graph else _default_output("layoutagent", task)
    args = ["--task", task]
    if image_path:
        args += ["--image", str(image_path)]
    args += ["--emit-scene-graph", str(out_path)]
    if provider:
        args += ["--provider", provider]
    if model:
        args += ["--model", model]

    proc = _run(LAYOUT_AGENT_DIR, LAYOUT_PYTHON, args, timeout)
    return _delegation_result("LayoutAgent", proc, out_path, _read_json(str(out_path)))


def run_arti_agent(
    task: str,
    *,
    image_path: str | None = None,
    emit_result: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Delegate a single object's geometry to ArtiAgent and return its emitted result.

    The result (asset_dir + real_bbox) is always written to BaseAgent/output/artiagent/ and
    returned in `result`; `emit_result` overrides that location if given.
    """
    nwords = len((task or "").split())
    if nwords > 8:
        print(f"[ArtiAgent] warning: task is {nwords} words — a terse (<=8 word) task "
              f"lets the structurer expand it and works better", file=sys.stderr)
    out_path = Path(emit_result) if emit_result else _default_output("artiagent", task)
    args = ["--task", task]
    if image_path:
        args += ["--image", str(image_path)]
    args += ["--emit-result", str(out_path)]
    if provider:
        args += ["--provider", provider]
    if model:
        args += ["--model", model]

    proc = _run(ARTI_AGENT_DIR, ARTI_PYTHON, args, timeout)
    return _delegation_result("ArtiAgent", proc, out_path, _read_json(str(out_path)))

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
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract import (
    validate_scene_graph,
    validate_placement_request,
    validate_asset_result,
    placement_request as build_placement_request,
)
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


def _run(project_dir: Path, python: str, args: list[str], timeout: int, cwd: Path | None = None) -> subprocess.CompletedProcess:
    # `-u` forces the child to unbuffered stdio so its prints reach us line-by-line
    # instead of sitting in an 8KB block buffer until the process exits.
    cmd = [python, "-u", str(project_dir / "main.py"), *args]
    name = project_dir.name
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd or project_dir),
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
    base = _slug(task)
    path = out / f"{base}.json"
    # Objects can share a name (e.g. three "dining chair" instances). Append a
    # numeric instance suffix instead of silently overwriting the previous result.
    i = 0
    while path.exists():
        i += 1
        path = out / f"{base}__{i}.json"
    return path


def _box_to_arg(box: dict) -> str:
    """Serialize a {center, dims, rpy} box dict to ArtiAgent's `--box` CLI string."""
    center = [float(v) for v in box.get("center", [])]
    dims = [float(v) for v in box.get("dims", [])]
    rpy = [float(v) for v in (box.get("rpy") or (0.0, 0.0, 0.0))]
    if len(center) != 3 or len(dims) != 3 or len(rpy) != 3:
        raise ValueError(f"box needs center/dims/rpy of 3 numbers each: {box!r}")
    parts = [*center, *dims]
    if any(abs(v) > 1e-9 for v in rpy):
        parts.extend(rpy)
    return ",".join(str(v) for v in parts)


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
    state_save_path: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Delegate scene layout to LayoutAgent and return its emitted scene graph.

    The scene graph (nodes/edges) is always written to BaseAgent/output/layoutagent/ and
    returned in `result`; `emit_scene_graph` overrides that location if given. When
    `state_save_path` is given, LayoutAgent also dumps its shared perception state
    (image / DA3 reconstruction / SAM3 masks / boxes) into that directory and its
    manifest.json is attached to the returned dict under the ``perception`` key.
    """
    nwords = len((task or "").split())
    if nwords > 8:
        print(f"[LayoutAgent] warning: task is {nwords} words — a terse (<=8 word) task "
              f"lets the structurer expand it and works better", file=sys.stderr)
    if emit_scene_graph:
        out_path = Path(emit_scene_graph)
    else:
        base = _default_output("layoutagent", task)
        out_path = base.with_name(f"{base.stem}-{time.strftime('%Y%m%d-%H%M%S')}{base.suffix}")
    # Deterministic perception-state directory: key by the image basename so the
    # orchestrating LLM's free-form name (e.g. "perception_state") cannot drift
    # between runs. The LLM's state_save_path value only signals "save it".
    if state_save_path and image_path:
        state_save_path = str(BASE_ROOT / "output" / "layoutagent" / Path(image_path).stem)

    args = ["--task", task]
    if image_path:
        args += ["--image", str(image_path)]
    args += ["--emit-scene-graph", str(out_path)]
    if state_save_path:
        args += ["--state-save-path", str(state_save_path)]
    if provider:
        args += ["--provider", provider]
    if model:
        args += ["--model", model]

    proc = _run(LAYOUT_AGENT_DIR, LAYOUT_PYTHON, args, timeout)
    payload = _read_json(str(out_path))
    out = _delegation_result("LayoutAgent", proc, out_path, payload)
    if payload is not None and out.get("ok"):
        errs = validate_scene_graph(payload)
        if errs:
            out["contract_errors"] = errs
    if state_save_path:
        perception = _read_json(str(Path(state_save_path) / "manifest.json"))
        if perception is not None:
            out["perception"] = perception
    return out


def run_arti_agent(
    task: str,
    *,
    image_path: str | None = None,
    emit_result: str | None = None,
    box: dict | None = None,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Delegate a single object's geometry to ArtiAgent and return its emitted result.

    The result (asset_dir + swept_bbox) is always written to BaseAgent/output/artiagent/ and
    returned in `result`; `emit_result` overrides that location if given. `box` (optional)
    is a {center, dims, rpy} dict that constrains the object's scale and position.
    """
    nwords = len((task or "").split())
    if nwords > 8:
        print(f"[ArtiAgent] warning: task is {nwords} words — a terse (<=8 word) task "
              f"lets the structurer expand it and works better", file=sys.stderr)
    out_path = Path(emit_result) if emit_result else _default_output("artiagent", task)

    # Versioned placement request: the Layout->Arti handoff, persisted for traceability.
    if box:
        req = build_placement_request(
            object_id=out_path.stem,
            label=task,
            box=box,
            image=image_path,
        )
        errs = validate_placement_request(req)
        if errs:
            print(f"[contract] invalid placement_request: {'; '.join(errs)}", file=sys.stderr)
        else:
            req_path = out_path.with_suffix(".placement.json")
            req_path.write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")

    args = ["--task", task]
    if image_path:
        args += ["--image", str(image_path)]
    args += ["--emit-result", str(out_path)]
    if box:
        args += ["--box", _box_to_arg(box)]
    if provider:
        args += ["--provider", provider]
    if model:
        args += ["--model", model]

    workdir = Path(tempfile.mkdtemp(prefix="arti_work_"))
    try:
        proc = _run(ARTI_AGENT_DIR, ARTI_PYTHON, args, timeout, cwd=workdir)
        payload = _read_json(str(out_path))
        out = _delegation_result("ArtiAgent", proc, out_path, payload)
        if payload is not None and out.get("ok"):
            errs = validate_asset_result(payload)
            if errs:
                out["contract_errors"] = errs
        return out
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_layout_apply_bboxes(
    scene_graph: dict,
    bboxes: list,
    *,
    task: str = "resolve collisions with the measured object sizes",
    emit_scene_graph: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Re-run LayoutAgent with measured rest/swept bboxes baked in.

    Writes a ``{schema_version, scene, bboxes}`` payload and delegates to LayoutAgent's
    ``--apply-bboxes`` mode: it scaffolds ``room.py`` from ``scene``, overrides each node's
    D with its rest bbox and attaches the swept bbox, then runs its normal
    write-compile-fix loop to resolve any new collision/floating. Returns the re-emitted
    scene graph.
    """
    out_path = Path(emit_scene_graph) if emit_scene_graph else _default_output("layoutagent", task)
    payload = {"schema_version": 1, "scene": scene_graph, "bboxes": bboxes}
    seed_path = out_path.with_suffix(".bboxes.json")
    seed_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    args = ["--task", task, "--apply-bboxes", str(seed_path), "--emit-scene-graph", str(out_path)]
    if provider:
        args += ["--provider", provider]
    if model:
        args += ["--model", model]
    proc = _run(LAYOUT_AGENT_DIR, LAYOUT_PYTHON, args, timeout)
    return _delegation_result("LayoutAgent", proc, out_path, _read_json(str(out_path)))


def _norm_key(s: str) -> str:
    """Normalize a name for fuzzy matching (lowercase, non-alnum -> single space)."""
    return re.sub(r"[^0-9a-z]+", " ", (s or "").lower()).strip()


def _match_box(boxes: dict, node_id: str):
    """Return the SAM3 box ([x1,y1,x2,y2]) whose key best matches ``node_id``, or None."""
    if not boxes or not node_id:
        return None
    if node_id in boxes:
        return boxes[node_id]
    target = _norm_key(node_id)
    if not target:
        return None
    for key, val in boxes.items():
        if _norm_key(key) == target:
            return val
    for key, val in boxes.items():
        k = _norm_key(key)
        if k and (target in k or k in target):
            return val
    return None


def _crop_object_image(
    image_path: str, boxes: dict, node_id: str, crop_dir: Path, pad: float = 0.1
) -> str | None:
    """Crop the input image to an object's SAM3 box (padded) and save a PNG.

    Returns the crop path, or None if no box matches / cropping fails — the caller
    then falls back to passing the full image.
    """
    box = _match_box(boxes, node_id)
    if box is None:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception:
        return None
    W, H = img.size
    try:
        x1, y1, x2, y2 = (int(round(float(v))) for v in box)
    except (TypeError, ValueError):
        return None
    x1, x2 = max(0, min(x1, x2)), min(W, max(x1, x2))
    y1, y2 = max(0, min(y1, y2)), min(H, max(y1, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    px = int(round((x2 - x1) * pad))
    py = int(round((y2 - y1) * pad))
    x1, x2 = max(0, x1 - px), min(W, x2 + px)
    y1, y2 = max(0, y1 - py), min(H, y2 + py)
    out = crop_dir / f"{_slug(node_id) or 'object'}.png"
    try:
        img.crop((x1, y1, x2, y2)).save(out)
    except Exception:
        return None
    return str(out)


def _object_label(name: str) -> str:
    """Turn a node/mask name into a short human text label for ArtiAgent.

    ``pillow_0`` -> ``pillow``, ``coffee table`` -> ``coffee table``, ``sofa_base``
    -> ``sofa base``. The trailing ``_<digits>`` is SAM3's instance index, not part of
    the object's identity.
    """
    s = re.sub(r"_\d+$", "", (name or "").strip())
    s = s.replace("_", " ").strip()
    return s or name


def _object_class(obj: dict) -> str:
    """Canonical class of an object, used to deduplicate identical instances.

    Prefers an explicit ``class`` field set by LayoutAgent on the object's nodes;
    otherwise falls back to the object's text label (already instance-index-stripped,
    e.g. ``chair_0`` -> ``chair``).
    """
    for node in obj.get("nodes") or []:
        klass = (node.get("class") or "").strip()
        if klass:
            return klass
    return obj.get("text") or obj.get("key") or "object"


def _mask_head(name: str) -> str:
    """First normalized token of a name (its semantic head)."""
    t = _norm_key(name)
    return t.split(" ")[0] if t else ""


def _match_mask(mask_names, node_id: str):
    """Return the SAM3 mask name (key) that best matches ``node_id``, or None.

    The LayoutAgent LLM names scene-graph nodes freely (``sofa_base``, ``sofa_back``),
    while SAM3 gives one coarse mask per object (``sofa``). This scores each mask name
    against the node id — exact > head-token > substring > shared token — so part-nodes
    collapse onto their single underlying mask.
    """
    if not mask_names or not node_id:
        return None
    names = list(mask_names)
    if node_id in names:
        return node_id
    target = _norm_key(node_id)
    thead = _mask_head(node_id)
    if not target:
        return None
    best, best_score = None, 0
    for name in names:
        n = _norm_key(name)
        if not n:
            continue
        score = 0
        if n == target:
            score = 100
        elif n == thead or _mask_head(name) == thead:
            score = 80
        elif n in target or target in n:
            score = 60
        else:
            shared = set(target.split(" ")) & set(n.split(" "))
            if shared:
                score = 40
        if score > best_score:
            best, best_score = name, score
    return best if best_score > 0 else None


def _node_box(node: dict):
    """Extract ``{center, dims, rpy}`` from a scene-graph node, or None if incomplete.

    The scene-graph ``theta`` is expressed in DEGREES (LayoutAgent schema.py); the box
    ``rpy`` is expressed in RADIANS (matching the URDF / viewer convention), so ``theta``
    is converted here.
    """
    try:
        center = [float(v) for v in (node.get("C") or [])]
        dims = [float(v) for v in (node.get("D") or [])]
        rpy = [math.radians(float(v)) for v in (node.get("theta") or [0.0, 0.0, 0.0])]
    except (TypeError, ValueError):
        return None
    if len(center) == 3 and len(dims) == 3:
        return {"center": center, "dims": dims, "rpy": rpy}
    return None


def _merge_boxes(boxes):
    """Merge several part-node OBBs into one axis-aligned bounding box.

    Used when one object was split into parts (e.g. sofa base/back/arms): the merged
    box covers the whole object, so ArtiAgent is constrained to the object's real scale.
    """
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    if len(boxes) == 1:
        return boxes[0]
    lo = [min(b["center"][i] - b["dims"][i] / 2 for b in boxes) for i in range(3)]
    hi = [max(b["center"][i] + b["dims"][i] / 2 for b in boxes) for i in range(3)]
    return {
        "center": [(lo[i] + hi[i]) / 2 for i in range(3)],
        "dims": [hi[i] - lo[i] for i in range(3)],
        "rpy": [0.0, 0.0, 0.0],
    }


def _mask_object_image(image_path: str, mask_path: str, out_path) -> str | None:
    """Composite a binary SAM3 mask over the image, isolating one object.

    Produces an RGBA PNG where the object's pixels are opaque and everything else is
    transparent, so ArtiAgent sees exactly that object (not its background or
    neighbours) and cannot re-segment it. Returns ``out_path``, or None on failure.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(image_path).convert("RGB")
        mask = np.asarray(np.load(mask_path)).astype(bool)
    except Exception:
        return None
    if mask.ndim != 2:
        return None
    W, H = img.size
    if mask.shape != (H, W):
        try:
            mask = np.asarray(
                Image.fromarray(mask.astype(np.uint8) * 255).resize((W, H), Image.NEAREST)
            ).astype(bool)
        except Exception:
            return None
    try:
        rgba = np.dstack([np.asarray(img), (mask * 255).astype(np.uint8)])
        Image.fromarray(rgba).save(out_path)
    except Exception:
        return None
    return str(out_path)


def orchestrate_reconstruct(
    image: str,
    task: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_workers: int | None = None,
) -> dict:
    """Phase 5 main flow: layout first, then per-object ArtiAgent in parallel.

    1. Run LayoutAgent on the full image, also saving its perception state so each
       object's SAM3 mask / box is available.
    2. From the returned scene graph, take every ``object`` node. The LayoutAgent LLM
       may split one object into parts (sofa -> ``sofa_base``/``sofa_back``/``sofa_arm_*``),
       while SAM3 gives one coarse mask per object (``sofa``). Group the part-nodes by
       their canonical SAM3 mask so each object is generated ONCE, not once per part.
    3. For each object, composite its binary mask over the image (only the object's
       pixels remain) and call ArtiAgent with the mask image + the object's text label
       (the mask name), constrained by the merged box of its part-nodes. Object nodes
       with no matching mask fall back to the full image + their node label.
    4. Aggregate ``{asset_dir, swept_bbox}`` per object.

    Returns ``{ok, layout, perception, objects, ...}`` for the orchestrating LLM.
    """
    layout_out = _default_output("layoutagent", task)
    perception_dir = layout_out.parent / (layout_out.stem + "_perception")

    # 1. layout (also dump perception state for per-object masks)
    layout = run_layout_agent(
        task,
        image_path=image,
        emit_scene_graph=str(layout_out),
        state_save_path=str(perception_dir),
        provider=provider,
        model=model,
        timeout=timeout,
    )
    if not layout.get("ok"):
        return {"ok": False, "stage": "layout", "layout": layout}

    scene_graph = layout.get("result") or {}
    nodes = scene_graph.get("nodes") or []
    object_nodes = [n for n in nodes if (n.get("type") or "").lower() == "object"]

    # 2. perception manifest: name -> mask relpath (e.g. "sofa" -> "masks/sofa.npy")
    manifest = layout.get("perception") or {}
    perception_root = Path(manifest["out_dir"]) if manifest.get("out_dir") else perception_dir
    mask_map = manifest.get("masks") or {}

    mask_dir = perception_root / "object_masks"
    mask_dir.mkdir(parents=True, exist_ok=True)

    arti_out = BASE_ROOT / "output" / "artiagent"
    arti_out.mkdir(parents=True, exist_ok=True)

    # 3. group object nodes by their canonical SAM3 mask; ungrouped = VLM-prior objects
    #    that SAM3 didn't segment (no mask/box) -> fall back to the full image.
    groups: dict = {}       # mask name -> list of part-node dicts
    group_mask: dict = {}   # mask name -> absolute .npy path
    ungrouped: list = []
    for node in object_nodes:
        node_id = node.get("id") or ""
        mask_name = _match_mask(mask_map, node_id)
        if mask_name and mask_map.get(mask_name):
            groups.setdefault(mask_name, []).append(node)
            group_mask.setdefault(mask_name, str(perception_root / mask_map[mask_name]))
        else:
            ungrouped.append(node)

    # Build one "object" record per real object (mask-grouped or ungrouped).
    objects_list: list = []
    for mask_name, part_nodes in groups.items():
        mask_img = _mask_object_image(image, group_mask[mask_name], mask_dir / f"{_slug(mask_name)}.png")
        objects_list.append({
            "key": mask_name,
            "text": _object_label(mask_name),
            "img": mask_img or image,
            "box": _merge_boxes([_node_box(n) for n in part_nodes]),
            "nodes": part_nodes,
        })
    for node in ungrouped:
        node_id = node.get("id") or f"object_{len(objects_list)}"
        objects_list.append({
            "key": node_id,
            "text": _object_label(node_id),
            "img": image,
            "box": _node_box(node),
            "nodes": [node],
        })

    # 3.5 group objects by canonical class so identical instances (e.g. three dining
    # chairs) are generated ONCE, then instantiated at each node's own placement.
    class_groups: dict = {}
    for obj in objects_list:
        klass = _object_class(obj)
        class_groups.setdefault(klass, []).append(obj)

    # 4. per-class generation (once) + per-object instantiation (placement).
    objects: dict = {}
    bboxes: list = []
    if class_groups:
        max_workers = max_workers or len(class_groups)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {}
            for klass, objs in class_groups.items():
                rep = objs[0]
                rep_path = arti_out / f"{layout_out.stem}__{_slug(rep['key'])}.json"
                fut = ex.submit(
                    run_arti_agent,
                    rep["text"],
                    image_path=rep["img"],
                    emit_result=str(rep_path),
                    box=rep["box"],
                    provider=provider,
                    model=model,
                    timeout=timeout,
                )
                futures[fut] = (klass, objs, rep_path)
            for fut in as_completed(futures):
                klass, objs, rep_path = futures[fut]
                try:
                    entry = fut.result()
                except Exception as e:
                    entry = {"agent": "ArtiAgent", "ok": False, "error": str(e)}
                result = entry.get("result") or {}
                asset_dir = result.get("asset_dir")
                rest = result.get("rest_bbox")
                swept = result.get("swept_bbox")
                dims = (rest or {}).get("dims")
                for i, obj in enumerate(objs):
                    node_ids = [n.get("id") for n in obj["nodes"]]
                    if rest and swept:
                        bboxes.append({"node_ids": node_ids, "rest": rest, "swept": swept})
                    if i == 0:
                        entry.setdefault("task", obj["text"])
                        entry.setdefault("node_ids", node_ids)
                        entry.setdefault("class", klass)
                        objects[obj["key"]] = entry
                        continue
                    box = obj.get("box") or {}
                    placement = {
                        "asset_dir": asset_dir,
                        "center": [round(float(v), 6) for v in (box.get("center") or (0.0, 0.0, 0.0))],
                        "dims": [round(float(v), 6) for v in (dims or (0.0, 0.0, 0.0))],
                        "rpy": [round(float(v), 6) for v in (box.get("rpy") or (0.0, 0.0, 0.0))],
                    }
                    path = arti_out / f"{layout_out.stem}__{_slug(obj['key'])}.json"
                    path.write_text(json.dumps(placement, ensure_ascii=False, indent=2), encoding="utf-8")
                    objects[obj["key"]] = {
                        "agent": "ArtiAgent",
                        "ok": entry.get("ok", False),
                        "output": str(path),
                        "result": placement,
                        "task": obj["text"],
                        "node_ids": node_ids,
                        "class": klass,
                    }

    refined = None
    if bboxes and scene_graph:
        refined = run_layout_apply_bboxes(
            scene_graph,
            bboxes,
            emit_scene_graph=str(layout_out.with_name(layout_out.stem + "_refined.json")),
            provider=provider,
            model=model,
            timeout=timeout,
        )

    # Gap 2: assemble the final instantiation — each node -> asset_dir + refined pose
    # (the "move the 3D asset to its pose" step). The refined scene graph is the single
    # source of truth for C/theta/D/swept_bbox; `objects` carries node_id -> asset_dir.
    #
    # The layout node's C is the bbox CENTER, but the URDF is authored with its origin
    # offset from that center (rest_bbox.center — e.g. a coffee table's origin is at the
    # legs while its bbox center sits at tabletop height). So the URDF origin is placed at
    #   C - R(yaw) @ rest.center
    # so the asset's bbox lands exactly on the node's OBB instead of floating above it.
    node_rest = {}
    for b in bboxes:
        rc = (b.get("rest") or {}).get("center") or [0.0, 0.0, 0.0]
        for nid in b.get("node_ids") or []:
            node_rest[nid] = rc

    placements = []
    if refined and refined.get("ok"):
        refined_nodes = (refined.get("result") or {}).get("nodes") or []
        node_asset = {}
        for obj in objects.values():
            ad = (obj.get("result") or {}).get("asset_dir")
            if not ad:
                continue
            for nid in obj.get("node_ids") or []:
                node_asset[nid] = ad
        for node in refined_nodes:
            nid = node.get("id")
            if nid not in node_asset:
                continue
            c = node.get("C") or [0.0, 0.0, 0.0]
            theta = node.get("theta") or [0.0, 0.0, 0.0]
            rc = node_rest.get(nid) or [0.0, 0.0, 0.0]
            # rotate the rest-center offset by yaw (theta[1], degrees) about +Y
            yaw = math.radians(float(theta[1]) if len(theta) > 1 else 0.0)
            cy, sy = math.cos(yaw), math.sin(yaw)
            off = (rc[0] * cy + rc[2] * sy, rc[1], -rc[0] * sy + rc[2] * cy)
            origin = [c[0] - off[0], c[1] - off[1], c[2] - off[2]]
            placements.append({
                "node_id": nid,
                "asset_dir": node_asset[nid],
                "center": [round(float(v), 6) for v in origin],
                "theta": theta,
                "dims": node.get("D"),
                "swept_bbox": node.get("swept_bbox"),
            })
        placements_path = layout_out.with_name(layout_out.stem + "_placements.json")
        placements_path.write_text(json.dumps(placements, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "layout": {"output": layout.get("output"), "result": scene_graph},
        "perception": manifest,
        "objects": objects,
        "refined": refined,
        "placements": placements,
    }

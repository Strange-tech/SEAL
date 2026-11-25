import json
import math
import os
import sys
import time
from pathlib import Path

# Schema version stamped on the emitted scene graph (keep in sync with BaseAgent/contract).
SCHEMA_VERSION = 1

from core import Agent
from basic_tools import ReadFileTool, WriteFileTool, EditFileTool, ListFilesTool, BashTool, restore
from memory import compose_system_prompt
from skill import discover_skills, SkillTool
from subagent import SubAgentTool
from tools.compile import CompileTool, load_scene_graph
from tools.node_merge import merge_contained_nodes, graph_to_py
from tools.fileio import ManhattanRegularizeTool
from tools.materialize import ExportObjTool, export_scene_graph
from tools.reconstruction import PerceptionState, Da3ReconstructTool, BackprojectObbTool
from tools.segmentation import Sam3SegmentTool
from tools.overlap_resolver import ResolveOverlapsTool, resolve_overlaps
from tools.write_perception import WritePerceptionStateTool, save_perception_state

REPO_ROOT = Path(__file__).resolve().parent

from agent.prompts import load_system_prompt_text, load_sdk_docs_reference
from agent.persistence import fork_context, write_success_record
from agent.structurer import should_structure, structure_task
from provider import Provider


HELP_TEXT = """Usage: python main.py [options]

Options:
  --help, -h          Show this help and exit
  --task <text>       Task text (required): the reconstruction instruction or a question about the room
  --image <path>      Input image path (optional)
  --emit-scene-graph <path>   Dump the final scene graph (nodes/edges JSON) to <path>
  --state-save-path <dir>  Save the perception state (image/reconstruction/masks/boxes) to <dir>
  --edit <room_id>    Edit an existing room (fork its room.py + lineage as the starting point)
  -c <session_id>     Resume an existing session (used with --task)
  --provider <name>   LLM provider: deepseek | qwen (default: PROVIDER env or deepseek)
  --model <id>        Model id override (default: per-provider env var or provider default)
  -restore <path>     Restore files (basic_tools.restore tool)

Environment:
  OPENAI_API_KEY      Required (DeepSeek key; DASHSCOPE_API_KEY for Qwen)
  PROVIDER            Provider name (default deepseek)
  MODEL               Model name (DeepSeek only, for backward compatibility)
  OPENAI_BASE_URL     API base URL (DeepSeek only; defaults to the provider's base URL)
"""


def ensure_model_scaffold() -> None:
    model_path = REPO_ROOT / "room.py"
    if model_path.exists():
        model_path.unlink()
    scaffold = REPO_ROOT / "scaffold.py"
    model_path.write_text(scaffold.read_text(encoding="utf-8"), encoding="utf-8")


def _vec_sub(a, b):
    return [float(a[i]) - float(b[i]) for i in range(3)]


def _vec_add(a, b):
    return [float(a[i]) + float(b[i]) for i in range(3)]


def _rot_yaw(v, theta):
    """Rotate a 3-vector by the yaw (theta[1], degrees) about +Y (upright objects)."""
    yaw = math.radians(float(theta[1]) if len(theta) > 1 else 0.0)
    c, s = math.cos(yaw), math.sin(yaw)
    x, y, z = v
    return (x * c + z * s, y, -x * s + z * c)


def apply_bboxes_to_graph(graph, bboxes, preserve_bottom=True):
    """Override each node's D from its rest bbox and attach swept_bbox for collision.

    ``bboxes`` is a list of ``{node_ids, rest:{center,dims}, swept:{center,dims}}``
    (both in the object's local frame). ``rest`` drives the rest footprint (node D);
    ``swept`` is the swept joint-range AABB, stored on the node as a world-space
    ``swept_bbox`` (center mapped through the node's C + yaw) so the collision check
    reserves the object's full motion envelope.

    When ``preserve_bottom`` is True (default), a changed rest height re-anchors the
    node's C so the bottom stays on the floor. Set it False when re-applying bboxes
    after the LLM's compile-fix loop, where the LLM's C is already the final placement
    and only D/swept_bbox need to be restored.
    """
    nodes = graph.get("nodes", [])
    by_id = {n.get("id"): n for n in nodes}
    for b in bboxes or []:
        rest = b.get("rest") or {}
        swept = b.get("swept") or {}
        for nid in b.get("node_ids") or []:
            n = by_id.get(nid)
            if not n:
                continue
            if rest.get("dims"):
                old_d = [float(v) for v in (n.get("D") or [0.0, 0.0, 0.0])]
                new_d = [float(v) for v in rest["dims"]]
                if preserve_bottom:
                    old_c = [float(v) for v in (n.get("C") or [0.0, 0.0, 0.0])]
                    # Keep the floor contact (bottom) along y and the center along x/z.
                    n["C"] = [
                        old_c[0],                                # x: keep center
                        old_c[1] + (new_d[1] - old_d[1]) / 2.0,  # y: keep bottom
                        old_c[2],                                # z: keep center
                    ]
                n["D"] = new_d
            if swept.get("dims"):
                off = _vec_sub(swept.get("center") or (0.0, 0.0, 0.0),
                               rest.get("center") or (0.0, 0.0, 0.0))
                wc = _vec_add(n.get("C") or (0.0, 0.0, 0.0),
                              _rot_yaw(off, n.get("theta") or (0.0, 0.0, 0.0)))
                n["swept_bbox"] = {
                    "center": [round(float(v), 6) for v in wc],
                    "dims": [float(v) for v in swept["dims"]],
                }
    return graph


def resolve_supports(graph, bboxes=None):
    """Re-stack supported objects on their supports after the feedback loop changed sizes.

    Handles only the vertical ("sitting on top") supports. For every ``supports`` edge
    (src supported by dst), place src's bottom exactly on dst's new top, keeping src's
    horizontal x/z from the layout. Wall-mounted supports (dst type == "wall") are left
    alone for now. When ``bboxes`` is provided, each re-positioned src's swept
    ``swept_bbox`` is recomputed at its new C so collision still sees the full envelope.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_id = {n.get("id"): n for n in nodes}

    support_of = {}
    for e in edges:
        if e.get("type") != "supports":
            continue
        dst = by_id.get(e.get("dst"))
        if dst and dst.get("type") == "wall":
            continue  # wall-mounted: out of scope (only vertical stacking for now)
        support_of[e.get("src")] = e.get("dst")
    if not support_of:
        return graph

    # swept - rest center offsets per node, for recomputing the swept_bbox.
    node_off = {}
    if bboxes:
        for b in bboxes:
            rest = (b.get("rest") or {}).get("center")
            swept = (b.get("swept") or {}).get("center")
            if rest is not None and swept is not None:
                off = _vec_sub(swept, rest)
                for nid in b.get("node_ids") or []:
                    node_off[nid] = off

    # topological order: a support before the objects it supports (DFS).
    order = []
    visited = set()

    def visit(nid):
        if nid in visited:
            return
        visited.add(nid)
        dst = support_of.get(nid)
        if dst and dst in support_of:
            visit(dst)
        order.append(nid)

    for src in support_of:
        visit(src)

    for src_id in order:
        src = by_id.get(src_id)
        dst = by_id.get(support_of.get(src_id))
        if not src or not dst:
            continue
        sd = [float(v) for v in (src.get("D") or [0.0, 0.0, 0.0])]
        dd = [float(v) for v in (dst.get("D") or [0.0, 0.0, 0.0])]
        dc = [float(v) for v in (dst.get("C") or [0.0, 0.0, 0.0])]
        sc = [float(v) for v in (src.get("C") or [0.0, 0.0, 0.0])]
        # src bottom = dst top
        sc[1] = dc[1] + dd[1] / 2.0 + sd[1] / 2.0
        src["C"] = [round(float(v), 6) for v in sc]
        # recompute swept_bbox world center at the new C
        if src_id in node_off and src.get("swept_bbox"):
            wc = _vec_add(sc, _rot_yaw(node_off[src_id], src.get("theta") or [0.0, 0.0, 0.0]))
            src["swept_bbox"] = {
                "center": [round(float(v), 6) for v in wc],
                "dims": src["swept_bbox"].get("dims"),
            }
    return graph


def main():
    raw_args = sys.argv[1:]

    if "--help" in raw_args or "-h" in raw_args:
        sys.stdout.write(HELP_TEXT)
        sys.exit(0)
    if not raw_args:
        sys.stderr.write(HELP_TEXT)
        sys.exit(1)
    if len(raw_args) == 2 and raw_args[0] == "-restore":
        sys.exit(restore(raw_args[1]))

    image_path = None
    emit_scene_graph = None
    state_save_path = None
    edit_room_id = None
    task = None
    resume_id = ""
    provider = None
    model = None
    apply_bboxes = None
    apply_bboxes_data = None
    i = 0
    while i < len(raw_args):
        a = raw_args[i]
        if a == "--image":
            if i + 1 >= len(raw_args):
                print("--image requires a path", file=sys.stderr)
                sys.exit(1)
            image_path = raw_args[i + 1]
            i += 2
        elif a.startswith("--image="):
            image_path = a.split("=", 1)[1]
            i += 1
        elif a == "--emit-scene-graph":
            if i + 1 >= len(raw_args):
                print("--emit-scene-graph requires a path", file=sys.stderr)
                sys.exit(1)
            emit_scene_graph = raw_args[i + 1]
            i += 2
        elif a.startswith("--emit-scene-graph="):
            emit_scene_graph = a.split("=", 1)[1]
            i += 1
        elif a == "--state-save-path":
            if i + 1 >= len(raw_args):
                print("--state-save-path requires a directory", file=sys.stderr)
                sys.exit(1)
            state_save_path = raw_args[i + 1]
            i += 2
        elif a.startswith("--state-save-path="):
            state_save_path = a.split("=", 1)[1]
            i += 1
        elif a == "--apply-bboxes":
            if i + 1 >= len(raw_args):
                print("--apply-bboxes requires a JSON path", file=sys.stderr)
                sys.exit(1)
            apply_bboxes = raw_args[i + 1]
            i += 2
        elif a.startswith("--apply-bboxes="):
            apply_bboxes = a.split("=", 1)[1]
            i += 1
        elif a == "--edit":
            if i + 1 >= len(raw_args):
                print("--edit requires a room id", file=sys.stderr)
                sys.exit(1)
            edit_room_id = raw_args[i + 1]
            i += 2
        elif a.startswith("--edit="):
            edit_room_id = a.split("=", 1)[1]
            i += 1
        elif a == "--task":
            if i + 1 >= len(raw_args):
                print("--task requires text", file=sys.stderr)
                sys.exit(1)
            task = raw_args[i + 1]
            i += 2
        elif a.startswith("--task="):
            task = a.split("=", 1)[1]
            i += 1
        elif a == "--provider":
            if i + 1 >= len(raw_args):
                print("--provider requires a provider name", file=sys.stderr)
                sys.exit(1)
            provider = raw_args[i + 1]
            i += 2
        elif a.startswith("--provider="):
            provider = a.split("=", 1)[1]
            i += 1
        elif a == "--model":
            if i + 1 >= len(raw_args):
                print("--model requires a model id", file=sys.stderr)
                sys.exit(1)
            model = raw_args[i + 1]
            i += 2
        elif a.startswith("--model="):
            model = a.split("=", 1)[1]
            i += 1
        elif a == "-c":
            if i + 1 >= len(raw_args):
                print("-c requires a session id", file=sys.stderr)
                sys.exit(1)
            resume_id = raw_args[i + 1]
            i += 2
        else:
            print(f"Unknown argument: {a}", file=sys.stderr)
            sys.stderr.write(HELP_TEXT)
            sys.exit(1)

    if not task:
        print("--task is required", file=sys.stderr)
        sys.stderr.write(HELP_TEXT)
        sys.exit(1)

    # Pass the DeepSeek key through when present; Provider resolves the per-provider
    # key (OPENAI_API_KEY for deepseek / DASHSCOPE_API_KEY for qwen) and validates it.
    api_key = os.environ.get("OPENAI_API_KEY", "")
    # empty base_url -> Provider resolves it per-provider (DEEPSEEK/QWEN default or *(_BASE_URL) override)
    base_url = os.environ.get("OPENAI_BASE_URL", "")

    provider = provider or os.environ.get("PROVIDER", "") or "deepseek"
    model = model or ""  # empty -> Provider resolves the per-provider env var / default model

    skills = discover_skills()

    state_image = str(Path(image_path).expanduser().resolve()) if image_path else None
    state = PerceptionState(state_image)

    # A dedicated provider for the overlap-resolver's VLM check (same model/key as the agent).
    vlm_provider = Provider(provider, model=model, api_key=api_key)
    vlm_provider.base_url = (base_url or vlm_provider.base_url).rstrip("/")
    overlap_resolver = lambda: resolve_overlaps(state, vlm_provider)

    tools = [
        ReadFileTool(), WriteFileTool(), EditFileTool(), ListFilesTool(), BashTool(),
        Sam3SegmentTool(state),
        Da3ReconstructTool(state),
        BackprojectObbTool(state, resolver=overlap_resolver),
        ResolveOverlapsTool(state, vlm_provider),
        WritePerceptionStateTool(state),
        ManhattanRegularizeTool(),
        CompileTool(path=str(REPO_ROOT / "room.py"), state=state, resolver=overlap_resolver),
        ExportObjTool(path=str(REPO_ROOT / "room.py")),
    ]
    if skills:
        tools.append(SkillTool(skills))
    tools.append(SubAgentTool(base_url, api_key, model, list(tools), skills, provider=provider))

    repo_root = REPO_ROOT

    _, designer_prompt = load_system_prompt_text(
        "designer_system_prompt.txt", provider="deepseek", sdk_package="sdk"
    )
    sdk_docs = load_sdk_docs_reference(repo_root, sdk_package="sdk")

    if image_path:
        perception_note = (
            "- An image IS attached: ground the scene with the perception pipeline "
            "(sam3_segment -> da3_reconstruct -> backproject_obb -> manhattan_regularize).\n"
            "- Run `resolve_overlaps` after `sam3_segment` and before `backproject_obb`; if it merges "
            "masks, emit ONE node for the merged object. Write the SAM3 mask name in each object "
            "node's `mask` field so `compile` can merge duplicate nodes.\n"
            "- When asked to save masks / perception, run `write_perception_state`.\n"
        )
    else:
        perception_note = (
            "- NO image is attached (text-only): skip `sam3_segment` / `da3_reconstruct` / "
            "`backproject_obb` and author `room.py` directly from the task text + the SDK docs.\n"
        )
    bbox_note = (
        "- Each node's D is the measured REST size (closed/resting pose) and swept_bbox is "
        "the swept size (full joint range, collision-only metadata). BOTH are already baked "
        "into room.py and are authoritative — do NOT change D or swept_bbox. Resolve any "
        "collision/floating by MOVING objects (adjust C / theta) only.\n"
        if apply_bboxes else ""
    )
    runtime_guidance = (
        "<runtime_task_guidance>\n"
        + perception_note
        + "- Snap resting objects to their support: bottom face exactly on the support's top "
        "(`C_y = support_top_y + D_y/2`), no rounding gap.\n"
        + "- For object nodes that are multiple instances of the same thing (e.g. three identical dining chairs), set a shared `class` field on each node (e.g. `class: \"dining chair\"`) so downstream generates the asset once and reuses it across instances.\n"
        + bbox_note
        + "</runtime_task_guidance>"
    )

    system_prompt = designer_prompt + "\n\n" + sdk_docs + "\n\n" + runtime_guidance

    # -- structure terse prompts into a scene-graph brief before the agent loop --
    if should_structure(task):
        try:
            struct_provider = Provider(provider, model=model, api_key=api_key)
            struct_provider.base_url = (base_url or struct_provider.base_url).rstrip("/")
            brief = structure_task(struct_provider, task, image_path=image_path)
        except Exception as e:
            print(f"Warning: structuring failed, using original prompt: {e}", file=sys.stderr)
        else:
            if brief:
                task = f"{task}\n\n<design_brief>\n{brief}\n</design_brief>"
                print(
                    f"[Structured brief added{' (image-grounded)' if image_path else ''}]",
                    file=sys.stderr,
                )

    if image_path:
        img_path = Path(image_path).expanduser().resolve()
        if not img_path.is_file():
            print(f"Error: image file not found: {img_path}", file=sys.stderr)
            sys.exit(1)
        user_content = [
            {"type": "text", "text": task},
            {"type": "input_image", "image_path": str(img_path)},
        ]
    else:
        user_content = task

    lineage = None
    if edit_room_id:
        room_text, lineage = fork_context(REPO_ROOT, edit_room_id)
        if room_text is None:
            print(f"Error: room {edit_room_id} not found or has no room.py", file=sys.stderr)
            sys.exit(1)
        (REPO_ROOT / "room.py").write_text(room_text, encoding="utf-8")
        print(f"[edit] forked {edit_room_id} into room.py", file=sys.stderr)
    elif apply_bboxes:
        # Feedback loop: seed room.py from the prior scene graph, then apply the measured
        # rest/swept bboxes (BaseAgent computed them from ArtiAgent's emitted result).
        data = json.loads(Path(apply_bboxes).read_text(encoding="utf-8"))
        apply_bboxes_data = data
        scene = data.get("scene") or {}
        bboxes = data.get("bboxes") or []
        graph = apply_bboxes_to_graph(scene, bboxes)
        resolve_supports(graph, bboxes)
        (REPO_ROOT / "room.py").write_text(graph_to_py(graph), encoding="utf-8")
        print(f"[apply-bboxes] seeded room.py from scene + {len(bboxes)} bboxes (supports re-solved)", file=sys.stderr)
    elif not resume_id:
        ensure_model_scaffold()

    agent = Agent(
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider,
        system_prompt=system_prompt,
        tools=tools,
    )
    exit_code = agent.run(user_content, resume_id)

    # Final safety-net merge: deterministically collapse object nodes that resolve to the
    # same overlap-merged mask, so the emitted scene graph / OBJ have one node per object
    # even if the agent's last compile was followed by a re-split edit.
    room_path = str(REPO_ROOT / "room.py")

    # Deterministic post-processing: the compile-fix loop may re-author room.py with the
    # WRONG sizes (confusing rest D with swept_bbox). Restore the measured rest/swept
    # bboxes + re-solve supports, keeping the LLM's adjusted positions.
    if apply_bboxes_data is not None:
        try:
            graph, gerr = load_scene_graph(room_path)
            if graph is not None and not gerr:
                graph = apply_bboxes_to_graph(graph, apply_bboxes_data.get("bboxes") or [], preserve_bottom=False)
                resolve_supports(graph, apply_bboxes_data.get("bboxes") or [])
                (REPO_ROOT / "room.py").write_text(graph_to_py(graph), encoding="utf-8")
                print("[apply-bboxes] restored measured sizes + supports after compile-fix", file=sys.stderr)
        except Exception as e:
            print(f"[apply-bboxes] post-process failed: {e}", file=sys.stderr)

    if getattr(state, "masks", None):
        try:
            overlap_resolver()  # idempotent; ensures mask_redirect is up to date
            graph, gerr = load_scene_graph(room_path)
            if graph is not None and not gerr:
                merged, merged_summary = merge_contained_nodes(graph, state)
                if merged_summary:
                    (REPO_ROOT / "room.py").write_text(graph_to_py(merged), encoding="utf-8")
                    print("[merge] final room.py: " + "; ".join(merged_summary), file=sys.stderr)
        except Exception as e:
            print(f"[merge] final merge skipped: {e}", file=sys.stderr)

    # Auto-materialize the final scene graph to room.obj after every run
    # (best-effort: a failed/partial room.py just leaves the previous OBJ in place).
    ok, message = export_scene_graph(room_path, out=str(REPO_ROOT / "room.obj"))
    if ok:
        print(f"[materialize] {message}", file=sys.stderr)
    else:
        print(f"[materialize] skipped: {message}", file=sys.stderr)

    # --emit-scene-graph: dump the final scene graph (nodes/edges) as JSON. Best-effort:
    # a failed/partial room.py just skips the dump (the subprocess caller treats it as absent).
    if emit_scene_graph:
        try:
            graph, error = load_scene_graph(room_path)
            if error:
                print(f"[emit-scene-graph] skipped: {error}", file=sys.stderr)
            else:
                emit_path = Path(emit_scene_graph).expanduser().resolve()
                emit_path.parent.mkdir(parents=True, exist_ok=True)
                graph["schema_version"] = SCHEMA_VERSION
                emit_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[emit-scene-graph] wrote {emit_path}", file=sys.stderr)
        except Exception as e:
            print(f"[emit-scene-graph] failed: {e}", file=sys.stderr)

    # --state-save-path: dump the shared perception state (image / DA3 reconstruction /
    # SAM3 masks / boxes) to a directory. Best-effort: a still-empty state just writes a bare
    # manifest; a failure must not change the process exit code.
    if state_save_path:
        try:
            manifest = save_perception_state(state, state_save_path)
            print(
                f"[state-save-path] wrote {manifest['out_dir']} "
                f"({len(state.masks or {})} masks, {len(state.boxes or {})} boxes)",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"[state-save-path] failed: {e}", file=sys.stderr)

    # Persist this run as a record (record + revision + provenance + lineage + manifest),
    # then materialize room.obj into the record's materialization dir. Best-effort: a
    # persistence failure must not change the process exit code.
    try:
        record_id, record_dir = write_success_record(
            repo_root=REPO_ROOT,
            prompt=task,
            provider=(agent.resolved_provider or provider),
            model_id=(agent.resolved_model or model or ""),
            image_path=image_path,
            max_turns=agent.max_rounds,
            lineage=lineage,
            turn_count=agent.turn_count,
            tool_call_count=agent.tool_call_count,
            compile_attempt_count=agent.compile_attempt_count,
            final_status="success" if exit_code == 0 else "failed",
            trajectory_path=agent.session_path,
        )
        print(f"[record] {record_id} -> {record_dir}", file=sys.stderr)
    except Exception as e:
        print(f"[record] skipped: {e}", file=sys.stderr)

    sys.exit(exit_code)


if __name__ == "__main__":
    start = time.perf_counter()
    try:
        main()
    finally:
        print(f"[Elapsed: {time.perf_counter() - start:.2f}s]", file=sys.stderr)

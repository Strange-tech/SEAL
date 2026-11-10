import json
import os
import sys
import time
from pathlib import Path

from core import Agent
from basic_tools import ReadFileTool, WriteFileTool, EditFileTool, ListFilesTool, BashTool, restore
from memory import compose_system_prompt
from skill import discover_skills, SkillTool
from subagent import SubAgentTool
from tools.compile import CompileTool, load_scene_graph
from tools.fileio import ManhattanRegularizeTool
from tools.materialize import ExportObjTool, export_scene_graph
from tools.reconstruction import PerceptionState, Da3ReconstructTool, BackprojectObbTool
from tools.segmentation import Sam3SegmentTool

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
    edit_room_id = None
    task = None
    resume_id = ""
    provider = None
    model = None
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
    tools = [
        ReadFileTool(), WriteFileTool(), EditFileTool(), ListFilesTool(), BashTool(),
        Sam3SegmentTool(state),
        Da3ReconstructTool(state),
        BackprojectObbTool(state),
        ManhattanRegularizeTool(),
        CompileTool(path=str(REPO_ROOT / "room.py"), state=state),
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

    runtime_guidance = (
        "<runtime_task_guidance>\n"
        "- Read the current `room.py` before editing.\n"
        "- SDK docs are read with `read_file` using the virtual paths in the preloaded quickstart "
        "index (e.g. docs/sdk/references/quickstart.md, docs/sdk/references/testing.md).\n"
        "- Build from grounded evidence: inspect the image, run `sam3_segment` per visible object, "
        "then `da3_reconstruct` for metric depth, backproject masks with `backproject_obb`, and snap "
        "orientations with `manhattan_regularize`.\n"
        "- Perception vs. VLM prior: `sam3_segment` + `da3_reconstruct` + `backproject_obb` give the "
        "accurate position (and accurate scale/orientation when the object is fully in frame). When an "
        "object is only partially in frame, perception's OBB is truncated — take the accurate position "
        "from perception, but complete the object's scale and orientation from the design brief's VLM "
        "prior.\n"
        "- Snap resting objects to their support: for every object linked by an `abuts` edge to a "
        "support (or resting on the reference surface), set its bottom face exactly to the support's top "
        "(`C_y = support_top_y + D_y/2`). Do not leave a small clearance/rounding gap — even a 1 cm gap "
        "is visually wrong on close-up shots.\n"
        "- Write a complete, compilable `room.py` in your FIRST `write_file` call (a full "
        "`build_scene_graph()` returning `nodes`/`edges`, not a stub), then iterate with small "
        "`edit_file` changes.\n"
        "- Do NOT probe the perception SDK or the scene-graph validator with one-off "
        "`bash python -c` commands. Author the scene graph directly in `room.py`; `compile` "
        "reports contract and usage errors for you.\n"
        "- Reconstruct only objects actually visible in the image, with real-world metric "
        "dimensions and orientations; no floating objects, no undeclared overlaps.\n"
        "- Run `compile` to check your latest revision.\n"
        "- If compile is clean and the scene graph already satisfies the visible-scene brief, "
        "conclude.\n"
        "</runtime_task_guidance>"
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

    # Auto-materialize the final scene graph to room.obj after every run
    # (best-effort: a failed/partial room.py just leaves the previous OBJ in place).
    room_path = str(REPO_ROOT / "room.py")
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
                emit_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[emit-scene-graph] wrote {emit_path}", file=sys.stderr)
        except Exception as e:
            print(f"[emit-scene-graph] failed: {e}", file=sys.stderr)

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

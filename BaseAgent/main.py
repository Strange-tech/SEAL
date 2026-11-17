"""BaseAgent — a minimal, self-contained agent entrypoint.

Wires together only the framework pieces (core loop + basic tools + memory +
budget + compression + subagent + session). It carries no domain tools or
domain prompt; build a concrete agent by adding tools and a system prompt on top.

Two run modes:
  - one-shot:  python main.py --task "..." [--image <path>]
  - REPL:      python main.py [--repl] [--image <path>]
               a long-running process: type a line, get a reply, repeat.
               The same session is reused across turns, so context/memory persist.
"""

import os
import sys
import time
from pathlib import Path

try:
    import readline  # arrow-key line editing + command history in the REPL
except ImportError:  # non-GNU/POSIX builds
    readline = None

from core import Agent
from basic_tools import ReadFileTool, WriteFileTool, EditFileTool, ListFilesTool, BashTool, restore
from memory import compose_system_prompt
from skill import discover_skills, SkillTool
from subagent import SubAgentTool
from provider import Provider
from agent.structurer import structure_task, TOOL_CAPABILITIES
from tools.call_subagent import CallLayoutAgentTool, CallArtiAgentTool, ReconstructSceneTool, set_current_image

REPO_ROOT = Path(__file__).resolve().parent

HELP_TEXT = """Usage: python main.py [options]

Modes:
  python main.py --task <text> [--image <path>]     one-shot run
  python main.py [--repl] [--image <path>]          interactive REPL (long-running session)

Options:
  --help, -h          Show this help and exit
  --task <text>       Task text (one-shot mode)
  --image <path>      Input image path (attached to the task / first REPL turn)
  --repl              Force interactive REPL mode (default when --task is absent)
  --stream            Stream the reply token-by-token (default in REPL mode)
  -c <session_id>     Resume an existing session
  --provider <name>   LLM provider: deepseek | qwen (default: PROVIDER env or deepseek)
  --model <id>        Model id override (default: per-provider env var or provider default)
  -restore <path>     Restore files (basic_tools.restore tool)

REPL commands:
  /help               Show this list
  /image <path> [task] Attach an image; trailing text is the task
  /new                Start a fresh session (drop accumulated context)
  /history            Show command history
  /exit, /quit        Exit the REPL

Environment:
  OPENAI_API_KEY      Required (DeepSeek key; DASHSCOPE_API_KEY for Qwen)
  PROVIDER            Provider name (default deepseek)
  MODEL               Model name (DeepSeek only, for backward compatibility)
  OPENAI_BASE_URL     API base URL (DeepSeek only; defaults to the provider's base URL)
"""

REPL_HELP = """REPL commands:
  /help               Show this list
  /image <path> [task] Attach an image; trailing text is the task
  /new                Start a fresh session (drop accumulated context)
  /history            Show command history
  /exit, /quit        Exit the REPL
"""


# --- pixel-art seal banner -------------------------------------------
_SEAL_PIXELS = [
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", None, None, None, None, None],
    [None, None, None, None, "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", None, None, None, None],
    [None, None, None, "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", None, None, None],
    [None, None, None, "#2ce8f5", "#ffffff", "#ffffff", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#ffffff", "#ffffff", "#2ce8f5", "#2ce8f5", None, None, None],
    [None, None, None, "#2ce8f5", "#ffffff", "#181425", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#ffffff", "#181425", "#2ce8f5", "#2ce8f5", None, None, None],
    [None, None, None, "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#0099db", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#0099db", None, "#0099db"],
    [None, None, None, "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", None, "#0099db", None],
    [None, None, None, "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#0099db", "#0099db", None],
    [None, None, None, "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#0099db", "#0099db", None],
    [None, None, None, "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#2ce8f5", "#0099db", None, None],
    [None, None, None, "#2ce8f5", "#2ce8f5", None, "#124e89", "#2ce8f5", "#2ce8f5", "#124e89", "#124e89", "#2ce8f5", "#2ce8f5", None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
]

_SEAL_COLORS = {
    "#2ce8f5": (44, 232, 245),   # cyan body
    "#ffffff": (255, 255, 255),  # white (eye sclera)
    "#181425": (24, 20, 37),     # near-black (pupil)
    "#0099db": (0, 153, 219),    # blue (flipper / nose)
    "#124e89": (18, 78, 137),    # navy (belly detail)
}

def _seal_banner() -> str:
    """Render the pixel seal with 24-bit ANSI color (half-block pixels)."""
    esc = chr(27)
    lines = []
    for i in range(0, len(_SEAL_PIXELS), 2):
        top = _SEAL_PIXELS[i]
        bottom = _SEAL_PIXELS[i + 1]
        cols = []
        for t, b in zip(top, bottom):
            if t is None and b is None:
                cols.append(" ")
            elif t is not None and b is not None:
                rt, gt, bt = _SEAL_COLORS[t]
                rb, gb, bb = _SEAL_COLORS[b]
                cols.append(f"{esc}[38;2;{rt};{gt};{bt}m{esc}[48;2;{rb};{gb};{bb}m▀{esc}[0m")
            elif t is not None:
                rt, gt, bt = _SEAL_COLORS[t]
                cols.append(f"{esc}[38;2;{rt};{gt};{bt}m▀{esc}[0m")
            else:
                rb, gb, bb = _SEAL_COLORS[b]
                cols.append(f"{esc}[38;2;{rb};{gb};{bb}m▄{esc}[0m")
        lines.append("".join(cols))
    return chr(10).join(lines)


def _resolve_model(provider: str, model: str) -> str:
    """Effective model id (mirrors provider.py priority chain)."""
    from provider import PROVIDERS
    spec = PROVIDERS.get((provider or "").strip().lower())
    if spec is None:
        return model or ""
    env_model = os.environ.get(spec.model_env, "")
    if not env_model and spec.honor_generic_model:
        env_model = os.environ.get("MODEL", "")
    return model or env_model or spec.default_model


def _startup_banner(provider: str, model: str, cwd: str) -> str:
    """Pixel seal with a 3-line info column to its right."""
    seal_lines = _seal_banner().split(chr(10))
    info = [
        "",
        "SEAL v0.0.1",
        "",
        f"[provider] {provider}   [model] {model}",
        "",
        cwd,
    ]
    gap = "   "
    out = []
    for i, line in enumerate(seal_lines):
        if i < len(info):
            out.append(line + gap + info[i])
        else:
            out.append(line)
    return chr(10).join(out)


def resolve_image(image_path):
    """Validate and absolutize an image path; return None if it is missing/invalid.

    Relative paths are tried against the current working directory first, then
    against the project root, so ``/image input/kid_room.png`` works no matter
    where ``python main.py`` was launched from.
    """
    if not image_path:
        return None
    p = Path(image_path).expanduser()
    candidates = [p] if p.is_absolute() else [p, REPO_ROOT / p]
    for cand in candidates:
        resolved = cand.resolve()
        if resolved.is_file():
            return str(resolved)
    tried = ", ".join(str(c.resolve()) for c in candidates)
    print(f"Error: image file not found: {image_path} (tried: {tried})", file=sys.stderr)
    return None


def build_user_content(task, image_path):
    """Build a turn's user content: plain text, or text + image parts.

    The image is sent to the model as pixels (base64), so its on-disk path would be lost.
    Surface the path in the text so the orchestrator can forward it to a sub-agent when
    delegating (the sub-agent needs the path, not the pixels).
    """
    if not image_path:
        return task
    text = f"{task}\n\n[attached image path: {image_path}]"
    return [
        {"type": "text", "text": text},
        {"type": "input_image", "image_path": image_path},
    ]


def _load_prompt_text(name: str) -> str:
    """Read agent/prompts/<name>.md; return "" (no error) if it is missing."""
    try:
        return (REPO_ROOT / "agent" / "prompts" / name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _make_structurer(provider_name, model, api_key, base_url):
    """Build a Provider for prompt structuring; return None if it cannot be created."""
    try:
        p = Provider(provider_name, model=model, api_key=api_key)
        p.base_url = (base_url or p.base_url).rstrip("/")
        return p
    except Exception:
        return None


def _structure_task(sp, task, image_path):
    """Expand the user task into an execution plan (prepended to the task); no-op if sp is None."""
    if sp is None:
        return task
    try:
        plan = structure_task(sp, task, image_path=image_path, tool_capabilities=TOOL_CAPABILITIES)
    except Exception as e:
        print(f"Warning: structuring failed, using original prompt: {e}", file=sys.stderr)
        return task
    if plan:
        task = f"{task}\n\n<execution_plan>\n{plan}\n</execution_plan>"
        print(f"[Structured plan added{' (image-grounded)' if image_path else ''}]", file=sys.stderr)
    return task


def build_agent(*, api_key, base_url, provider, model, stream):
    skills = discover_skills()
    tools = [
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        ListFilesTool(),
        BashTool(),
    ]
    if skills:
        tools.append(SkillTool(skills))
    # Child tools for the sub-agent: the current tool set (basic tools + skill),
    # deliberately excluding the SubAgentTool itself to avoid recursive fan-out.
    tools.append(SubAgentTool(base_url, api_key, model, list(tools), skills, provider=provider))
    # Project orchestration tools (top-level only, not passed to sub-agents):
    # delegate a whole task to LayoutAgent / ArtiAgent as a subprocess.
    tools.append(CallLayoutAgentTool())
    tools.append(CallArtiAgentTool())
    tools.append(ReconstructSceneTool())

    system_prompt = (
        "<base_agent>\n"
        "You are the SEAL orchestrator. You delegate to two sub-agents via tools: "
        "call_layout_agent (whole-image segmentation + room reconstruction -> scene graph), "
        "call_arti_agent (single-object articulated asset), and reconstruct_scene (the end-to-end "
        "pipeline: layout first, then per-box parallel ArtiAgent). Use the file tools "
        "(read_file / write_file / edit_file / list_files / bash) only to inspect the workspace. "
        "Read before editing, and verify your changes.\n"
        "</base_agent>"
    )
    for name in ("tools_instruction.md", "system.md"):
        extra = _load_prompt_text(name)
        if extra:
            system_prompt += "\n\n---\n\n" + extra
    system_prompt += compose_system_prompt(skills)

    return Agent(
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider,
        system_prompt=system_prompt,
        tools=tools,
        stream=stream,
    )


def run_repl(agent, initial_image, initial_task=None, struct_provider=None):
    print("BaseAgent REPL. Type /help for commands.", file=sys.stderr)
    resume_id = ""
    image_path = initial_image
    task = initial_task

    # Command history. `history` is the in-memory buffer backing /history and the
    # up/down-arrow navigation; readline provides the actual line editing (left/right
    # arrows move the cursor, up/down arrows walk the history). Both stay in sync.
    history = []
    history_file = Path(os.environ.get("BASEAGENT_HISTFILE") or (Path.home() / ".baseagent_history"))
    if readline is not None:
        readline.set_history_length(1000)
        try:
            loaded = history_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            loaded = []
        history.extend(loaded)
        for cmd in loaded:
            readline.add_history(cmd)

    try:
        while True:
            if task is None:
                try:
                    line = input(">>> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not line:
                    continue
                history.append(line)
                if readline is not None:
                    readline.add_history(line)
                low = line.lower()
                if low in ("/exit", "/quit"):
                    break
                if low == "/help":
                    print(REPL_HELP)
                    continue
                if low == "/history":
                    for i, cmd in enumerate(history, 1):
                        print(f"{i:4d}  {cmd}")
                    continue
                if low == "/new":
                    resume_id = ""
                    image_path = None
                    print("[session reset]", file=sys.stderr)
                    continue
                if low.startswith("/image "):
                    arg = line[len("/image "):].strip()
                    parts = arg.split(maxsplit=1)
                    image_path = resolve_image(parts[0])
                    if image_path:
                        print(f"[image set: {image_path}]", file=sys.stderr)
                        if len(parts) > 1 and parts[1].strip():
                            task = parts[1].strip()
                    continue
                task = line

            task = _structure_task(struct_provider, task, image_path)
            content = build_user_content(task, image_path)
            set_current_image(image_path)
            try:
                agent.run(content, resume_id)
            finally:
                set_current_image(None)
            if agent.session_id:
                resume_id = agent.session_id  # reuse the session across turns
            # an attached image (if any) applies to exactly one turn, then clears
            task = None
            image_path = None
    finally:
        if readline is not None:
            try:
                readline.write_history_file(str(history_file))
            except OSError:
                pass


def main():
    raw_args = sys.argv[1:]

    if "--help" in raw_args or "-h" in raw_args:
        sys.stdout.write(HELP_TEXT)
        sys.exit(0)
    if len(raw_args) == 2 and raw_args[0] == "-restore":
        sys.exit(restore(raw_args[1]))

    task = None
    image_path = None
    resume_id = ""
    provider = None
    model = None
    repl_mode = False
    stream_flag = False
    i = 0
    while i < len(raw_args):
        a = raw_args[i]
        if a in ("--task", "--image", "--provider", "--model"):
            if i + 1 >= len(raw_args):
                print(f"{a} requires a value", file=sys.stderr)
                sys.exit(1)
            val = raw_args[i + 1]
            if a == "--task":
                task = val
            elif a == "--image":
                image_path = val
            elif a == "--provider":
                provider = val
            else:
                model = val
            i += 2
        elif a == "-c":
            if i + 1 >= len(raw_args):
                print("-c requires a session id", file=sys.stderr)
                sys.exit(1)
            resume_id = raw_args[i + 1]
            i += 2
        elif a.startswith("--task="):
            task = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--image="):
            image_path = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--provider="):
            provider = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--model="):
            model = a.split("=", 1)[1]
            i += 1
        elif a == "--repl":
            repl_mode = True
            i += 1
        elif a == "--stream":
            stream_flag = True
            i += 1
        else:
            print(f"Unknown argument: {a}", file=sys.stderr)
            sys.stderr.write(HELP_TEXT)
            sys.exit(1)

    # no --task -> interactive REPL
    if task is None and not repl_mode:
        repl_mode = True

    image_path = resolve_image(image_path)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    provider = provider or os.environ.get("PROVIDER", "") or "deepseek"
    model = model or ""

    # streaming: default on in REPL, opt-in via --stream in one-shot
    stream = stream_flag or repl_mode

    agent = build_agent(api_key=api_key, base_url=base_url, provider=provider, model=model, stream=stream)
    struct_provider = _make_structurer(provider, model, api_key, base_url)

    if repl_mode:
        model_label = _resolve_model(provider, model)
        print(_startup_banner(provider, model_label, os.getcwd()), file=sys.stderr)
        run_repl(agent, image_path, initial_task=task, struct_provider=struct_provider)
        sys.exit(0)

    task = _structure_task(struct_provider, task, image_path)
    content = build_user_content(task, image_path)
    set_current_image(image_path)
    exit_code = agent.run(content, resume_id)
    sys.exit(exit_code)


if __name__ == "__main__":
    start = time.perf_counter()
    try:
        main()
    finally:
        print(f"[Elapsed: {time.perf_counter() - start:.2f}s]", file=sys.stderr)

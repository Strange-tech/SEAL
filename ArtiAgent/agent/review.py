"""Post-run self-improvement reviewer (Reflexion-style).

After ``main.py`` finishes a generation run, this standalone CLI reads a session
transcript from ``.sessions/*.jsonl``, distills a compact "signal" (tool histogram,
compile timeline, deduped error strings, API-rediscovery probes), and asks an
independent reviewer model (default ``deepseek-v4-pro``) to identify recurring,
prompt-fixable problems.

Findings that a prompt/skill can fix become reusable skills written to
``.harness-skills/<slug>.md`` (the exact format ``skill_layer`` loads). Findings
that need a code or environment change are reported to the user (printed + appended to
``REVIEW_NOTES.md``) and are never auto-edited.

The reviewer only PROPOSES; this script decides and writes. Skills are not auto-accepted
unless the reviewer is confident enough, and duplicates against existing skills are
skipped.

Usage:
    python agent/review.py                # review the latest session
    python agent/review.py --session <id> # review a specific session id
    python agent/review.py --dry-run      # run the reviewer but write nothing
    python agent/review.py --no-llm       # only preprocess + print the signal
    python agent/review.py --force        # re-review even if already reviewed
"""

from __future__ import annotations

import argparse
import difflib
import importlib
import json
import os
import re
import sys
import time
from pathlib import Path

# The Windows console defaults to GBK (cp936); emit UTF-8 (matching the log and
# the tool-capture layer) and replace unencodable chars instead of crashing when
# we print the reviewer's (possibly non-GBK) text.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent  # repo root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from provider import get_provider  # noqa: E402
from skill_layer import discover_skills  # noqa: E402
from agent.persistence import active_model_text  # noqa: E402

SESSION_DIR = ROOT / ".sessions"
SKILLS_ROOT = ROOT / ".harness-skills"
STATE_FILE = ROOT / ".review_state.json"
NOTES_FILE = ROOT / "REVIEW_NOTES.md"

DEFAULT_REVIEW_MODEL = "deepseek-v4-pro"
DEFAULT_PROVIDER = "deepseek"

MAX_ERRORS = 40
MAX_SIGNATURE_PROBES = 30


# --------------------------------------------------------------------------- #
# Session loading + deterministic signal extraction
# --------------------------------------------------------------------------- #

def _clip(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 3] + "..."


def find_latest_session() -> Path | None:
    files = [p for p in SESSION_DIR.glob("*.jsonl") if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def resolve_session(session_arg: str | None) -> Path:
    if session_arg and session_arg.strip().lower() == "latest":
        session_arg = None
    if session_arg:
        p = Path(session_arg)
        if not p.is_file():
            p = SESSION_DIR / (session_arg if session_arg.endswith(".jsonl") else session_arg + ".jsonl")
        if not p.is_file():
            raise SystemExit(f"Session not found: {session_arg}")
        return p
    latest = find_latest_session()
    if latest is None:
        raise SystemExit("No session files found under .sessions/")
    return latest


def load_messages(path: Path) -> list[dict]:
    messages: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") == "message" and rec.get("message") is not None:
                messages.append(rec["message"])
    return messages


def _tool_name(tc: dict) -> str:
    fn = tc.get("function") or {}
    return fn.get("name", "") or ""


def _tool_args(tc: dict) -> str:
    fn = tc.get("function") or {}
    return fn.get("arguments", "") or ""


def _arg_path(args_str: str) -> str:
    try:
        params = json.loads(args_str) if args_str else {}
    except json.JSONDecodeError:
        return "?"
    return str(params.get("path", "?"))


def _parse_compile_signals(content: str) -> dict:
    summary = ""
    m = re.search(r"<summary>\s*(.*?)\s*</summary>", content, re.S)
    if m:
        summary = _clip(m.group(1).replace("\n", " | "), 300)
    if "status=failure" in content:
        status = "failure"
    elif "status=success" in content:
        status = "success"
    else:
        status = "unknown"
    kinds = re.findall(r"^\s*-\s+(?:FAILURE|WARNING|NOTE)\s+\[([^\]]+)\]", content, re.M)
    return {"status": status, "summary": summary, "kinds": kinds[:8]}


def _extract_errors(content: str, tool: str) -> list[str]:
    """Pull the stable, meaningful error lines out of a tool result."""
    out: list[str] = []
    m = re.search(r"Probe error \[([^\]]+)\]:\s*(.+)", content)
    if m:
        out.append(f"[{m.group(1)}] {_clip(m.group(2), 200)}")
    # The deepest exception line of a traceback is the most stable error text.
    for line in reversed(content.splitlines()):
        s = line.strip()
        if not s:
            continue
        if re.match(
            r"^(?:TypeError|ValueError|KeyError|AttributeError|NameError|RuntimeError|"
            r"NotImplementedError|ImportError|ModuleNotFoundError|OSError|Exception):\b",
            s,
        ):
            out.append(_clip(s, 200))
            break
    for mm in re.finditer(r"unexpected keyword argument '[^']*'", content):
        out.append(mm.group(0))
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("Error:") and len(s) <= 300:
            out.append(_clip(s, 200))
    if tool == "bash" and "command not found" in content.lower():
        out.append("bash: command not found")
    if "command not done" in content.lower():
        out.append("BRep_API: command not done (degenerate boolean operation)")
    return out


def extract_signal(messages: list[dict]) -> dict:
    id_to_name: dict[str, str] = {}
    hist: dict[str, int] = {}
    read_paths: dict[str, int] = {}
    compile_results: list[dict] = []
    errors: list[dict] = []
    seen_errors: set[str] = set()
    signature_probes: list[dict] = []

    round_no = 0
    sig_probes_by_id: dict[str, dict] = {}
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            round_no += 1
            for tc in m.get("tool_calls") or []:
                name = _tool_name(tc)
                if not name:
                    continue
                hist[name] = hist.get(name, 0) + 1
                tid = tc.get("id")
                if tid:
                    id_to_name[tid] = name
                args_str = _tool_args(tc)
                if name == "read_file":
                    p = _arg_path(args_str)
                    read_paths[p] = read_paths.get(p, 0) + 1
                elif name == "probe_model" and ("inspect.signature" in args_str or "inspect." in args_str):
                    entry = {"round": round_no, "snippet": _clip(args_str, 240), "revealed": ""}
                    signature_probes.append(entry)
                    if tid:
                        sig_probes_by_id[tid] = entry
            continue
        if role == "tool":
            tid = m.get("tool_call_id")
            name = id_to_name.get(tid, "?")
            content = m.get("content") or ""
            if tid in sig_probes_by_id and not content.startswith("Probe error"):
                # Capture the runtime-revealed API signature as ground truth for the reviewer.
                sig_probes_by_id[tid]["revealed"] = _clip(content, 500)
            if name == "compile_model":
                compile_results.append({"round": round_no, **_parse_compile_signals(content)})
            for err in _extract_errors(content, name):
                key = err.casefold()
                if key not in seen_errors:
                    seen_errors.add(key)
                    errors.append({"round": round_no, "tool": name, "text": err})

    # Max gap (in rounds) between consecutive compiles ~ unvalidated edit-batch size.
    compile_rounds = [c["round"] for c in compile_results]
    max_compile_gap = 0
    if len(compile_rounds) >= 2:
        max_compile_gap = max(b - a for a, b in zip(compile_rounds, compile_rounds[1:]))

    return {
        "total_rounds": round_no,
        "tool_histogram": hist,
        "read_paths": {k: v for k, v in sorted(read_paths.items(), key=lambda kv: -kv[1])},
        "compile_timeline": compile_results,
        "max_rounds_between_compiles": max_compile_gap,
        "errors": errors[:MAX_ERRORS],
        "signature_probes": signature_probes[:MAX_SIGNATURE_PROBES],
    }


# --------------------------------------------------------------------------- #
# Reviewer prompt + call
# --------------------------------------------------------------------------- #

REVIEWER_SYSTEM = """\
You are the post-run self-improvement reviewer for "ArticraftAgent", an agent that
generates articulated 3D objects by editing a single `model.py` with a small toolset
(read_file, edit_file, write_file, bash, compile_model, probe_model, find_examples).

You review a distilled transcript of ONE completed run. Your job is reflection, not
model-building: find concrete problems that wasted rounds or caused repeated failure,
and decide whether each is fixable by a reusable prompt/skill or needs a code/environment
change.

The base prompt ALREADY covers this generic guidance, so a skill that merely restates any
of it is worthless and must NOT be emitted:
- compile after substantive edits (the agent was already told to do this);
- avoid floating / disconnected parts and unintentional overlaps;
- when unsure of an SDK/CadQuery API name, use probe_model with inspect.signature instead
  of guessing.
Only propose a skill when you have a SPECIFIC, concrete fact the base prompt lacks.

Strict rules:
1. A "skill" finding MUST teach a concrete, reusable correction — an exact API signature,
   parameter name, call pattern, or equivalent — grounded in evidence from this transcript
   or in API facts you are certain of. NEVER invent or guess an API signature, parameter
   name, or SDK fact. If the best advice you have is generic ("be more careful", "compile
   more often", "verify before calling"), use type "ignore" instead of "skill". If you are
   not certain of the correct concrete answer, do NOT write the skill — emit a
   "code_change" finding asking for human verification.
2. When a `signature_probes` entry has a non-empty `revealed` value, that value is the
   ground-truth API signature the agent discovered at runtime. You may copy it verbatim
   into a skill_body — this is exactly the concrete fact a skill should teach.
3. Ignore one-off mistakes. A skill is worth adding only when the same trap is likely to
   recur (repeated within this run, or a clear general API/usage pitfall).
4. "code_change" findings are for problems no prompt can fix: missing dependencies,
   tool/SDK bugs, harness crashes, or anything needing human review.
5. Skills must be concise and general — a reusable correction, not a recap of this run.
   `skill_description` is ONE line, written as "<UPPERCASE TRIGGER SCENARIO> — <verb + the
   concrete fact>" (e.g. "ENGRAVING TEXT — use cq.Workplane.text(txt, fontsize, distance,
   combine=...)" ). The trigger phrase must let the agent recognize from the scenario words
   alone that this skill applies; keep it short and self-discoverable. `skill_body` is the
   full instruction the agent loads on demand.

Return ONLY a JSON object with this exact shape (no prose, no markdown fences):
{
  "verdict": "short overall assessment (1-2 sentences)",
  "findings": [
    {
      "type": "skill" | "code_change" | "ignore",
      "title": "short human-readable name",
      "problem": "one line: what went wrong",
      "evidence": "round numbers / error strings / tool counts from the transcript",
      "skill_name": "kebab-case slug (only for type=skill)",
      "skill_description": "one line: '<UPPERCASE TRIGGER> — <verb + fact>' for the menu (only for type=skill)",
      "skill_body": "the reusable instruction (only for type=skill)",
      "code_note": "what the human should do (only for type=code_change)"
    }
  ]
}
"""


def build_reviewer_user(signal: dict, existing_skills: dict) -> str:
    existing = {
        name: sk.description for name, sk in existing_skills.items()
    } if existing_skills else {}
    return (
        "Below is the distilled transcript of a completed ArticraftAgent run.\n\n"
        "<signal>\n"
        f"{json.dumps(signal, ensure_ascii=False, indent=2)}\n"
        "</signal>\n\n"
        "Existing skills already on disk (do NOT duplicate these; only extend one if a "
        "finding genuinely augments it):\n"
        f"{json.dumps(existing, ensure_ascii=False, indent=2) if existing else '(none)'}\n\n"
        "Skill files use this exact format (frontmatter with a `description` key, then the "
        "body):\n"
        "---\n"
        "description: <one line>\n"
        "---\n"
        "<body>\n\n"
        "Remember: return ONLY the JSON object. No markdown fences, no commentary."
    )


def call_reviewer(provider, signal: dict, existing_skills: dict) -> dict:
    history = [
        {"role": "system", "content": REVIEWER_SYSTEM},
        {"role": "user", "content": build_reviewer_user(signal, existing_skills)},
    ]
    r = provider.send(history)
    msg = r["choices"][0].get("message") or {}
    text = msg.get("content") or msg.get("reasoning_content") or ""
    if not text.strip():
        raise RuntimeError("Reviewer returned empty content")
    return parse_findings(text)


def parse_findings(text: str) -> dict:
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"reviewer returned invalid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("reviewer output is not a JSON object")
    return data


FIX_BUGS_SYSTEM = """\
You are the "user-guided skill distiller" for ArticraftAgent, an agent that generates
articulated 3D objects by editing a single `model.py` (CadQuery + the local `sdk`).

The user just ran an `--edit` on an existing asset and explicitly marked it as a bug fix
(`--fix_bugs fix_bugs`). This is a human-validated correction, so the change is
authoritative. Your job is to distill the generalizable, reusable lesson from this specific
fix into AT MOST ONE skill, so future runs stop making the same mistake.

You are given:
- the user's fix request (what was wrong / what to change), and
- a unified diff between the parent model.py and the fixed model.py.

Strict rules:
1. Emit AT MOST ONE "skill" finding. If the diff is only cosmetic, numeric tweaks, or
   asset-specific proportions with no reusable API/technique lesson, emit ZERO findings and
   say so in the verdict.
2. The skill MUST teach a concrete, reusable correction — an exact API signature, parameter
   name, call pattern, or technique — grounded in the diff. NEVER invent or guess an API
   signature or SDK fact that is not present in the diff. If you are not certain of the
   concrete correct form, emit a "code_change" finding asking for human review instead.
3. Generalize: do not recap this specific asset. Capture the pattern of CadQuery/SDK usage
   the fix demonstrates that OTHER assets could reuse.
4. `skill_description` is ONE line, written as "<UPPERCASE TRIGGER SCENARIO> — <verb + the
   concrete fact>". The trigger phrase must let the agent recognize from the scenario words
   alone that this skill applies.
5. `skill_body` is the concise, reusable instruction with the exact API signature/pattern.

Return ONLY a JSON object with this exact shape (no prose, no markdown fences):
{
  "verdict": "short overall assessment (1-2 sentences)",
  "findings": [
    {
      "type": "skill" | "code_change",
      "title": "short human-readable name",
      "problem": "one line: what was wrong",
      "evidence": "which part of the diff fixed it",
      "skill_name": "kebab-case slug (only for type=skill)",
      "skill_description": "one line: '<UPPERCASE TRIGGER> — <verb + fact>' (only for type=skill)",
      "skill_body": "the reusable instruction (only for type=skill)",
      "code_note": "what the human should do (only for type=code_change)"
    }
  ]
}
"""


def _unified_diff(before: str, after: str, max_chars: int = 12000) -> str:
    diff = list(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="parent/model.py", tofile="fixed/model.py", lineterm="",
    ))
    text = "\n".join(diff)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[diff truncated]..."
    return text


def build_fix_bugs_user(task: str, diff: str, existing_skills: dict) -> str:
    existing = {
        name: sk.description for name, sk in existing_skills.items()
    } if existing_skills else {}
    return (
        "The user marked this edit as a bug fix. Distill the reusable lesson into a skill.\n\n"
        "<fix_request>\n"
        f"{(task or '').strip() or '(no task text)'}\n"
        "</fix_request>\n\n"
        "<diff>\n"
        f"{diff}\n"
        "</diff>\n\n"
        "Existing skills already on disk (do NOT duplicate these; only extend one if a "
        "finding genuinely augments it):\n"
        f"{json.dumps(existing, ensure_ascii=False, indent=2) if existing else '(none)'}\n\n"
        "Skill files use this exact format (frontmatter with a `description` key, then the "
        "body):\n"
        "---\n"
        "description: <one line>\n"
        "---\n"
        "<body>\n\n"
        "Remember: return ONLY the JSON object. No markdown fences, no commentary."
    )


def call_fix_bugs_skill(provider, parent_text: str, child_text: str, task: str, existing_skills: dict) -> dict:
    diff = _unified_diff(parent_text, child_text)
    history = [
        {"role": "system", "content": FIX_BUGS_SYSTEM},
        {"role": "user", "content": build_fix_bugs_user(task, diff, existing_skills)},
    ]
    r = provider.send(history)
    msg = r["choices"][0].get("message") or {}
    text = msg.get("content") or msg.get("reasoning_content") or ""
    if not text.strip():
        raise RuntimeError("Skill distiller returned empty content")
    return parse_findings(text)


# --------------------------------------------------------------------------- #
# Applying findings: write skills + notes
# --------------------------------------------------------------------------- #

def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "skill"


def write_skill(name: str, description: str, body: str) -> Path:
    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    p = SKILLS_ROOT / f"{name}.md"
    p.write_text(
        f"---\ndescription: {description.strip()}\n---\n{body.strip()}\n",
        encoding="utf-8",
    )
    return p


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"reviewed": {}}
    return {"reviewed": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_notes(session_id: str, notes: list[dict]) -> None:
    header = f"\n\n## Review of session `{session_id}` ({time.strftime('%Y-%m-%d %H:%M:%S')})\n"
    body = header + "\n".join(f"- **{n.get('title', 'code change')}**: {n.get('note', '')}" for n in notes)
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(body)


# --------------------------------------------------------------------------- #
# Skill fact verification (guard against reviewer API hallucinations)
# --------------------------------------------------------------------------- #

# Namespace-qualified references worth verifying: cadquery.selectors.OrSelector,
# sdk.mesh_from_cadquery, cq.Workplane.text, ...
_SYMBOL_RE = re.compile(r"\b(?:cadquery|cq|sdk|OCP|ocp|cq_occ)(?:\.[A-Za-z_]\w*)+\b")

# Words that make a "X does not exist" statement a correct negative claim.
_NEGATION_RE = re.compile(
    r"(?i)\b(no|not|without|isn['’]?t|doesn['’]?t|does not|there is no|never|"
    r"absent|missing|no such|unavailable)\b"
)


def _resolve_dotted_symbol(symbol: str) -> tuple[bool, str]:
    """Resolve a dotted reference like ``cadquery.selectors.OrSelector`` to a live object.

    Returns ``(ok, detail)``. ``ok`` is True only if every segment resolves.
    """
    parts = symbol.split(".")
    if parts[0] == "cq":
        parts[0] = "cadquery"
    module = None
    consumed = 0
    for i in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:i]))
            consumed = i
            break
        except (ImportError, ModuleNotFoundError):
            continue
    if module is None:
        return False, f"{symbol!r} cannot be imported"
    obj: object = module
    for attr in parts[consumed:]:
        try:
            obj = getattr(obj, attr)
        except AttributeError:
            return False, f"{symbol!r} has no attribute {attr!r}"
        except Exception as exc:  # lazy __getattr__ may raise anything
            return False, f"{symbol!r}: resolving {attr!r} raised {type(exc).__name__}"
    return True, ""


def _symbol_occurrences(text: str, symbol: str):
    start = 0
    while True:
        idx = text.find(symbol, start)
        if idx < 0:
            return
        yield idx
        start = idx + len(symbol)


def _is_negated(text: str, idx: int) -> bool:
    return bool(_NEGATION_RE.search(text[max(0, idx - 60):idx]))


def verify_skill_facts(description: str, body: str) -> list[str]:
    """Return rejection reasons when a proposed skill cites a non-existent API symbol.

    Only namespace-qualified references (cadquery / cq / sdk / OCP / ...) are checked.
    A missing symbol that is explicitly negated ("there is no X") is a correct negative
    claim and is allowed; a missing symbol used positively ("use X") is a hallucination
    and is rejected. Empty list => every fact resolves.
    """
    text = f"{description}\n{body}"
    reasons: list[str] = []
    seen: set[str] = set()
    for symbol in _SYMBOL_RE.findall(text):
        if symbol in seen:
            continue
        seen.add(symbol)
        ok, detail = _resolve_dotted_symbol(symbol)
        if ok:
            continue
        # Reject only if at least one mention is a positive (non-negated) use.
        mentions = list(_symbol_occurrences(text, symbol))
        if any(not _is_negated(text, idx) for idx in mentions):
            reasons.append(detail)
    return reasons


def apply_findings(findings: list[dict], session_id: str, existing_names: set[str], dry_run: bool) -> tuple[list[str], list[dict]]:
    created: list[str] = []
    notes: list[dict] = []
    for f in findings:
        ftype = f.get("type")
        if ftype == "skill":
            name = slugify(f.get("skill_name") or f.get("title") or "unnamed")
            desc = (f.get("skill_description") or "").strip()
            body = (f.get("skill_body") or "").strip()
            if not desc or not body:
                continue
            if name in existing_names:
                print(f"  [skip] skill '{name}' already exists", file=sys.stderr)
                continue
            # Guard: reject skills that cite a non-existent API symbol (reviewer
            # hallucination). A missing symbol used negatively ("there is no X")
            # is allowed; one used positively ("use X") is rejected and surfaced
            # to the human as a code note instead of being written.
            reject = verify_skill_facts(desc, body)
            if reject:
                print(f"  [reject] skill '{name}' cites a non-existent API:", file=sys.stderr)
                for r in reject:
                    print(f"           - {r}", file=sys.stderr)
                notes.append({
                    "title": f.get("title", "rejected skill"),
                    "note": (
                        f"Reviewer proposed skill '{name}' but it cites a non-existent API "
                        f"({'; '.join(reject)}). Verify the correct API and hand-write the skill."
                    ),
                })
                continue
            if dry_run:
                print(f"  [would write] skill '{name}': {desc}", file=sys.stderr)
                print(f"    --- body ---\n{_clip(body, 1500)}\n    --- end body ---", file=sys.stderr)
            else:
                write_skill(name, desc, body)
                print(f"  [wrote] skill '{name}': {desc}", file=sys.stderr)
            created.append(name)
        elif ftype == "code_change":
            note = (f.get("code_note") or f.get("problem") or "").strip()
            if not note:
                continue
            notes.append({"title": f.get("title", "code change"), "note": note})
            print(f"  [code_change] {note}", file=sys.stderr)
    if notes and not dry_run:
        append_notes(session_id, notes)
    return created, notes


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def run_fix_bugs(args) -> int:
    if not args.parent or not args.child:
        print("Error: --fix-bugs requires --parent <record_id> and --child <record_id>", file=sys.stderr)
        return 1
    parent_text = active_model_text(ROOT, args.parent)
    child_text = active_model_text(ROOT, args.child)
    if parent_text is None:
        print(f"Error: parent record has no active model.py: {args.parent}", file=sys.stderr)
        return 1
    if child_text is None:
        print(f"Error: child record has no active model.py: {args.child}", file=sys.stderr)
        return 1

    task = (args.task or "").strip()
    session_id = args.session or args.child
    if session_id.endswith(".jsonl"):
        session_id = session_id[:-6]
    session_id = session_id.replace("\\", "/").split("/")[-1]

    existing = discover_skills()
    existing_names = set(existing.keys())

    provider = get_provider(args.provider, model=args.model)
    print(f"[fix-bugs] parent={args.parent}", file=sys.stderr)
    print(f"[fix-bugs] child={args.child}", file=sys.stderr)
    print(f"[reviewer] {provider.name} / {provider.model}", file=sys.stderr)
    try:
        data = call_fix_bugs_skill(provider, parent_text, child_text, task, existing)
    except Exception as e:
        print(f"Error: fix-bugs skill distillation failed: {e}", file=sys.stderr)
        return 1

    verdict = data.get("verdict", "")
    findings = data.get("findings") or []
    print(f"\n=== Fix-bugs skill distillation ({args.child}) ===\n{verdict}\n")

    created, notes = apply_findings(findings, session_id, existing_names, args.dry_run)
    print(f"\nDone: {len(created)} skill(s) proposed, {len(notes)} code-change note(s)."
          + (" (dry-run: nothing written)" if args.dry_run else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-run self-improvement reviewer")
    ap.add_argument("--session", help="Session id (or path) to review; default: latest")
    ap.add_argument("--provider", default=DEFAULT_PROVIDER, help=f"Reviewer provider (default: {DEFAULT_PROVIDER})")
    ap.add_argument("--model", default=DEFAULT_REVIEW_MODEL, help=f"Reviewer model (default: {DEFAULT_REVIEW_MODEL})")
    ap.add_argument("--dry-run", action="store_true", help="Run the reviewer but write nothing")
    ap.add_argument("--no-llm", action="store_true", help="Only preprocess and print the signal; skip the reviewer")
    ap.add_argument("--force", action="store_true", help="Re-review even if the session was already reviewed")
    ap.add_argument("--fix-bugs", action="store_true", help="Distill a reusable skill from a bug-fix edit (requires --parent, --child, --task)")
    ap.add_argument("--parent", help="Parent record id (the --edit source)")
    ap.add_argument("--child", help="Child record id (the fixed result)")
    ap.add_argument("--task", help="The user's fix request text")
    args = ap.parse_args()

    os.chdir(ROOT)
    if args.fix_bugs:
        return run_fix_bugs(args)
    session_path = resolve_session(args.session)
    session_id = session_path.stem
    print(f"[session] {session_id}", file=sys.stderr)

    messages = load_messages(session_path)
    signal = extract_signal(messages)
    if args.no_llm:
        print(json.dumps(signal, ensure_ascii=False, indent=2))
        return 0

    state = load_state()
    if session_id in state.get("reviewed", {}) and not args.force:
        print(f"[skip] session {session_id} already reviewed (use --force to re-review)", file=sys.stderr)
        return 0

    existing = discover_skills()
    existing_names = set(existing.keys())

    provider = get_provider(args.provider, model=args.model)
    print(f"[reviewer] {provider.name} / {provider.model}", file=sys.stderr)
    try:
        data = call_reviewer(provider, signal, existing)
    except Exception as e:
        print(f"Error: review failed: {e}", file=sys.stderr)
        return 1

    verdict = data.get("verdict", "")
    findings = data.get("findings") or []
    print(f"\n=== Verdict ({session_id}) ===\n{verdict}\n")

    created, notes = apply_findings(findings, session_id, existing_names, args.dry_run)

    if not args.dry_run:
        reviewed = state.setdefault("reviewed", {})
        reviewed[session_id] = {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "created_skills": created,
            "code_notes": len(notes),
        }
        save_state(state)

    print(f"\nDone: {len(created)} skill(s) proposed, {len(notes)} code-change note(s)."
          + (" (dry-run: nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
import os
import sys
import time
import subprocess
from pathlib import Path
from agent.compiler import compile_urdf_report_maybe_timeout
from agent.feedback import render_compile_signals, compile_signal_bundle_from_exception
from agent.model_contract import missing_required_model_contract
from agent.probe_layer import run_probe
from agent.examples import search_examples
from agent.workspace_docs import build_virtual_workspace

# --- Tool Layer ---

DEFAULT_BASH_TIMEOUT = 30
MAX_BASH_TIMEOUT = 120
MAX_BASH_OUTPUT = 8 * 1024

WORK_DIR = os.getcwd()

TRASH_DIR = ".trash"

MODEL_FILENAME = "model.py"


def _model_file_abs() -> str:
    return os.path.abspath(os.path.join(WORK_DIR, MODEL_FILENAME))


def _is_model_file(path) -> bool:
    """True when `path` (relative or absolute) resolves to the harness `model.py`."""
    try:
        return os.path.abspath(os.path.join(WORK_DIR, str(path))) == _model_file_abs()
    except (OSError, ValueError):
        return False


def _validate_python_syntax(code: str, filename: str = "<string>") -> dict:
    """Syntax-check `code` via `compile()` and return a `compilation` status dict."""
    try:
        compile(code, filename, "exec")
        return {"status": "success", "error": None}
    except SyntaxError as e:
        return {
            "status": "error",
            "error": f"Syntax error: {e.msg} (line {e.lineno})",
            "error_line": e.lineno,
        }
    except Exception as e:
        return {"status": "error", "error": f"Validation error: {str(e)}"}


def _compilation_suffix(compilation: dict) -> str:
    return " | compilation: " + json.dumps(compilation, ensure_ascii=False)


class ReadFileTool:
    def __init__(self, repo_root=None, sdk_package="sdk"):
        self._repo_root = Path(repo_root) if repo_root else Path(WORK_DIR)
        self._sdk_package = sdk_package
        self._ws = None

    def _get_workspace(self):
        if self._ws is None:
            self._ws = build_virtual_workspace(self._repo_root, model_file_path=self._repo_root / "model.py", sdk_package=self._sdk_package)
        return self._ws

    def definition(self):
        return {
            "name": "read_file",
            "description": (
                "Read an exact file from the virtual workspace with 1-indexed line numbers. "
                "Use path='model.py' for the model artifact, or a docs/sdk/references/... path "
                "for preloaded SDK guidance; any other path falls back to a direct disk read. "
                "Returned lines are formatted as 'L{line}: ...'. Use offset (1-indexed) to start "
                "at a specific line and limit to cap the number of returned lines; omit both for "
                "a full-file read. Must read the file first before modifying it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path of the file to read"},
                    "offset": {"type": "integer", "description": "Optional. 1-indexed line to start from. Omit for 1."},
                    "limit": {"type": "integer", "description": "Optional. Maximum number of lines to return. Omit for EOF."},
                },
                "required": ["path"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args)
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        path = params.get("path", "")
        offset = params.get("offset")
        limit = params.get("limit")

        if offset is not None:
            try:
                offset = int(offset)
            except (TypeError, ValueError):
                return "Error: offset must be an integer"
            if offset < 1:
                return "Error: offset must be >= 1"
        if limit is not None:
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                return "Error: limit must be an integer"
            if limit < 1:
                return "Error: limit must be >= 1"

        # Resolve full text: virtual workspace first, then direct disk read.
        try:
            vf = self._get_workspace().resolve(path)
        except (ValueError, FileNotFoundError):
            vf = None
        if vf is not None:
            try:
                full_code = vf.read_text()
            except OSError as e:
                return "Error: " + str(e)
        else:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    full_code = f.read()
            except OSError as e:
                return "Error: " + str(e)

        split = full_code.splitlines()
        if not split:
            if offset is not None and offset > 1:
                return "Error: offset exceeds file length"
            return ""
        if offset is not None and offset > len(split):
            return "Error: offset exceeds file length"

        start = (offset if offset is not None else 1) - 1
        end = min(len(split), start + limit) if limit is not None else len(split)
        return "\n".join(f"L{idx}: {split[idx - 1]}" for idx in range(start + 1, end + 1))

class WriteFileTool:
    def definition(self):
        return {
            "name": "write_file",
            "description": (
                "Write full content to a file, creating it if needed. When the target is "
                "model.py, the content must satisfy the complete top-level contract "
                "(build_object_model, run_tests, object_model = build_object_model()) or the "
                "write is refused; Python syntax is validated and reported as a compilation "
                "status (a syntax error does not block the write). For any other file, the "
                "write is a plain overwrite with a backup."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path of the file to write"},
                    "content": {"type": "string", "description": "Full text content to write"},
                },
                "required": ["path", "content"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args)
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        path = params.get("path", "")
        content = params.get("content", "")
        is_model = _is_model_file(path)

        if is_model:
            missing = missing_required_model_contract(content)
            if missing:
                return "Error: write_file must include the complete top-level model.py contract: " + ", ".join(missing)
            compilation = _validate_python_syntax(content, filename=MODEL_FILENAME)

        try:
            backup = backup_if_exists(path)
        except OSError as e:
            return "Error: Failed to back up old content. Refusing to overwrite for safety: " + str(e)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return "Error: " + str(e)

        size = len(content.encode("utf-8"))
        if backup:
            msg = f"Old content backed up to {backup}, then writing to {path} ({size} bytes)."
        else:
            msg = f"Written to {path} ({size} bytes)"
        if is_model:
            msg += _compilation_suffix(compilation)
        return msg

class EditFileTool:
    def definition(self):
        return {
            "name": "edit_file",
            "description": (
                "Replace an exact literal string (old_string) with new_string in a file. "
                "old_string must match EXACTLY, including whitespace and indentation. By default "
                "old_string must appear exactly once; if it appears multiple times, provide a "
                "longer unique string or set replace_all=true. When the target is model.py, the "
                "edit must preserve the complete top-level contract (build_object_model, run_tests, "
                "object_model = build_object_model()) or the edit is refused; Python syntax is "
                "validated and reported as a compilation status. An empty old_string initializes a "
                "currently-empty file with new_string."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to target file"},
                    "old_string": {"type": "string", "description": "Original text to search for"},
                    "new_string": {"type": "string", "description": "New text for replacement; can be empty (to delete)"},
                    "replace_all": {"type": "boolean", "description": "If false (default), old_string must appear exactly once. If true, replace all occurrences."},
                },
                "required": ["path", "old_string", "new_string"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args)
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        path = params.get("path", "")
        old = params.get("old_string", "")
        new = params.get("new_string", "")
        replace_all = bool(params.get("replace_all"))
        is_model = _is_model_file(path)

        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            return "Error: " + str(e)

        # Empty old_string -> initialize an empty file with new_string (full-code path).
        if old == "":
            if text.strip():
                return "Error: old_string cannot be empty unless the file is empty. Please provide the exact string to replace."
            new_code = new
            if is_model:
                missing = missing_required_model_contract(new_code)
                if missing:
                    return "Error: edit_file must initialize model.py with the complete top-level contract: " + ", ".join(missing)
                compilation = _validate_python_syntax(new_code, filename=MODEL_FILENAME)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_code)
            except OSError as e:
                return "Error: " + str(e)
            msg = "Code edited successfully"
            if is_model:
                msg += _compilation_suffix(compilation)
            return msg

        if old not in text:
            return "Error: Could not find old_string in the code. Make sure the string matches exactly, including whitespace and indentation."

        occurrences = text.count(old)
        if occurrences > 1 and not replace_all:
            return f"Error: old_string appears {occurrences} times in the file. Provide a longer, unique string that appears only once, or use replace_all=true."

        if replace_all:
            new_code = text.replace(old, new)
        else:
            new_code = text.replace(old, new, 1)

        if is_model:
            missing = missing_required_model_contract(new_code)
            if missing:
                return "Error: edit_file must preserve the complete top-level model.py contract: " + ", ".join(missing)
            compilation = _validate_python_syntax(new_code, filename=MODEL_FILENAME)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_code)
        except OSError as e:
            return "Error: " + str(e)

        if replace_all and occurrences > 1:
            msg = f"Code edited successfully (replaced {occurrences} occurrences)"
        else:
            msg = "Code edited successfully"
        if is_model:
            msg += _compilation_suffix(compilation)
        return msg

class ListFilesTool:
	def definition(self):
		return {
			"name": "list_files",
			"description": "List all files under the current directory.",
			"parameters": {
				"type": "object",
				"properties": {
					"path": {"type": "string", "description": "Path of the current directory."},
				},
				"required": ["path"],		
			},
		}
	def execute(self, args):
		try:
			params = json.loads(args)
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		try:	
			dir_path = params.get("path", "")
			entries = os.listdir(dir_path)
			return "\n".join(entries)
		except OSError as e:
			return "Error: " + str(e)

class BashTool:
	def definition(self):
		return {
			"name": "bash",
			"description": "Run a command in the system shell and return stdout and stderr."
							"The command always executes in a fixed working directory; cd does not persist across invocations."
							"Default timeout is 30 seconds; pass timeout (integer seconds, maximum 120) if longer runtime is expected."
							"Prefer dedicated tools read_file / write_file / edit_file for tasks that can be accomplished with them."
							"Do not use redirection or sed to modify files. File modifications must use edit_file.",
			"parameters": {
				"type": "object",
				"properties": {
					"command": {"type": "string", "description": "Shell command to be executed."},
					"timeout": {"type": "integer", "description": "Timeout in seconds, optional. Defaults to 30, maximum 120."},
				},
				"required": ["command"],
			},
		}
	def execute(self, args):
		try:
			params = json.loads(args)
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		command = params.get("command", "") or ""
		if not command.strip():
			return "Error: Command can not be empty"
		d = DEFAULT_BASH_TIMEOUT
		timeout_arg = params.get("timeout") or 0
		if timeout_arg > 0:
			d = timeout_arg
			if d > MAX_BASH_TIMEOUT:
				return (f"Error: timeout maximum is {MAX_BASH_TIMEOUT} seconds."
					"To run longer commands, split the task into smaller parts or avoid waiting for it in a single call.")

		try:
			result = subprocess.run(
				command,
				shell=True,
				cwd=WORK_DIR,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				timeout=d,
			)
		except subprocess.TimeoutExpired as e:
			text = tail(e.stdout or b"", MAX_BASH_OUTPUT)
			return f"Error: Command exceeded {d} seconds and was terminated. Output before kill:\n{text}"

		text = tail(result.stdout, MAX_BASH_OUTPUT)
		if result.returncode != 0:
			return f"{text}\n[exit status {result.returncode}]"
		if text == "":
			return "Success command, no output"
		return text

class CompileModelTool:
	def definition(self):
		return {
			"name": "compile_model",
			"description": (
				"Run full model compile and QC on the current model.py.\n\n"
				"Use this after one or more edits when you want full compile/test feedback.\n"
				"The harness automatically runs baseline sanity/QC checks for model validity, "
				"exactly one root part, mesh assets, floating disconnected part groups, "
				"disconnected geometry islands inside a part, and current-pose real 3D overlaps.\n"
				"Do not manually author that baseline stack in run_tests(); reserve run_tests() "
				"for exact checks, targeted poses, and explicit allowances.\n\n"
				"The tool returns the same structured <compile_signals> block used by the harness "
				"for clean success, warnings, or failures."
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
			return render_compile_signals(report.signal_bundle)
		except Exception as e:
			return render_compile_signals(compile_signal_bundle_from_exception(e))


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


class FindExamplesTool:
	def __init__(self, examples_dir=None):
		self._examples_dir = examples_dir

	def _resolve_examples_dir(self):
		if self._examples_dir is not None:
			return Path(self._examples_dir)
		try:
			import sdk as _sdk
			return Path(_sdk.__file__).resolve().parent / "_examples"
		except Exception:
			return Path(WORK_DIR) / "sdk" / "_examples"

	def definition(self):
		return {
			"name": "find_examples",
			"description": (
				"Run lexical search over curated example documents for the active SDK and "
                "return sufficiently relevant full markdown matches.\n\n"
                "Search checks file names, titles, descriptions, tags, prose, and code "
                "identifiers. It works best with short concrete queries such as object names, "
                "feature names, geometry operations, CadQuery API names, or exact example "
                "titles.\n\n"
                "When strong matches do not exist, the tool may return `[weakly relevant]` "
                "results as inspiration-only hints. Treat those cautiously.\n\n"
                "This does not search SDK docs, tests, test helper APIs, or arbitrary "
                "repository code. It is not a general API search tool.\n\n"
                "If relevance is weak, the search may return fewer than limit results."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"query": {"type": "string", "description": "Keywords describing the pattern to search for"},
					"limit": {"type": "integer", "description": "Maximum number of full example documents to return. Search may return fewer if relevance is weak."},
				},
				"required": ["query"],
			},
		}

	def execute(self, args):
		try:
			params = json.loads(args)
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		query = params.get("query", "") or ""
		if not query.strip():
			return "Error: query cannot be empty"
		limit = params.get("limit") or 3
		return search_examples(
			query,
			examples_dir=self._resolve_examples_dir(),
			limit=int(limit),
		)


def tail(data, max_bytes):
	if len(data) <= max_bytes:
		return data.decode("utf-8", errors="replace")
	cut = data[-max_bytes:]
	i = cut.find(b"\n")
	if i >= 0:
		cut = cut[i+1:]
	skipped = len(data) - len(cut)
	return f"[... {skipped} bytes truncated from the front, only the tail is preserved ...]\n" + cut.decode("utf-8", errors="replace")


def backup_if_exists(path):
	if not os.path.exists(path):
		return ""
	os.makedirs(TRASH_DIR, exist_ok=True)
	with open(path, "rb") as f:
		data = f.read()
	ts = time.strftime("%Y%m%d-%H%M%S")
	dest = os.path.join(TRASH_DIR, f"{ts}_{os.path.basename(path)}")
	with open(dest, "wb") as f:
		f.write(data)
	return dest

def restore(path):
	try:
		entries = os.listdir(TRASH_DIR)
	except OSError as e:
		print(f"Error: Directory {TRASH_DIR} not found, or read failed: {e}", file=sys.stderr)
		return 1
	suffix = "_" + os.path.basename(path)
	newest = ""
	for name in entries:
		if name.endswith(suffix) and name > newest:
			newest = name
	if not newest:
		print(f"Error: {TRASH_DIR} doesn't have the backup of {os.path.basename(path)}", file=sys.stderr)
		return 1
	try:
		backup_if_exists(path)
	except OSError as e:
		print(f"Error: Failed to back up current version. Refusing restoration for safety: {e}", file=sys.stderr)
		return 1
	src = os.path.join(TRASH_DIR, newest)
	try:
		with open(src, "rb") as f:
			data = f.read()
		with open(path, "wb") as f:
			f.write(data)
	except OSError as e:
		print(f"Error: {e}", file=sys.stderr)
		return 1
	print(f"Restored from {src} to {path}")
	return 0


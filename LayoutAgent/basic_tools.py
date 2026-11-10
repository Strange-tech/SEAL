import json
import os
import sys
import time
import subprocess

# --- Tool Layer ---

DEFAULT_BASH_TIMEOUT = 30
MAX_BASH_TIMEOUT = 120
MAX_BASH_OUTPUT = 8 * 1024

WORK_DIR = os.getcwd()

TRASH_DIR = ".trash"

class ReadFileTool:
	def definition(self):
		return {
			"name": "read_file",
			"description": "Read a file and return its text content. Must read the file first before modifying it.",
			"parameters": {
				"type": "object",
				"properties": {
					"path": {"type": "string", "description": "Path of the file to read"},
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
			with open(params.get("path", ""), encoding="utf-8", errors="replace") as f:
				return f.read()
		except OSError as e:
			return "Error: " + str(e)

class WriteFileTool:
	def definition(self):
		return {
			"name": "write_file",
			"description": "Write full content to a file. Create the file if it does not exist; overwrite the entire file if it exists.",
			"parameters": {
				"type": "object",
				"properties": {
					"path": {"type": "string", "description": "Path of the file to write"},
					"content": {"type": "string", "description": "Full text content to write"},
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
		content = params.get("content", "")
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
			return f"Old content backed up to {backup}, then writing to {path} ({size} bytes)."
		return f"Written to {params.get('path')} ({len(content.encode('utf-8'))} bytes)"

class EditFileTool:
	def definition(self):
		return {
			"name": "edit_file",
			"description": "Replace matched text (old_string) with new_string in an existing file. Normally the target text appears exactly once. If multiple matches exist, replace all occurrences. Return a message if no match found. File must already exist (use write_file to create new files).",
			"parameters": {
				"type": "object",
				"properties": {
					"path": {"type": "string", "description": "Path to target file"},
					"old_string": {"type": "string", "description": "Original text to search for"},
					"new_string": {"type": "string", "description": "New text for replacement; can be empty (to delete)"},
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
		try:
			with open(path, encoding="utf-8") as f:
				text = f.read()
		except OSError as e:
			return "Error: " + str(e)
		if old == "":
			return "Error: old_string cannot be empty"
		n = text.count(old)
		if n == 0:
			return "Error: old_string not found in file"
		text = text.replace(old, new)
		try:
			with open(path, "w", encoding="utf-8") as f:
				f.write(text)
		except OSError as e:
			return "Error: " + str(e)

		if n > 1:
			return f"Warning: old_string occurs {n} times, attempting to replace all"
		return "Replaced matching text in " + path

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
	def __init__(self, work_dir=None):
		self.work_dir = work_dir or WORK_DIR

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
				cwd=self.work_dir,
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

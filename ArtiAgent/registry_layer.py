import os
import json
import sys

# --- Registry Layer ---

DECISION_ALLOW = 0
DECISION_ASK = 1
DECISION_DENY = 2
BASH_RULES = [
    ("rm -rf /", DECISION_DENY),          # Linux
    ("rmdir", DECISION_DENY),  # Windows cmd
    ("rm -rf ~", DECISION_DENY),          # Linux
    ("rm -rf", DECISION_ASK),             # Linux
    ("rmdir /s /q", DECISION_ASK),        # Windows cmd
    ("cmd /c del", DECISION_ASK),        # Windows cmd
    ("sudo ", DECISION_ASK),              # Linux
    ("powershell -Command Start-Process -Verb RunAs", DECISION_ASK), # Windows提权
    ("git push --force", DECISION_ASK),   # 跨平台git，共用
    ("curl ", DECISION_ASK),              # 跨平台
    ("ls", DECISION_ALLOW),               # Linux / Git Bash
    ("dir", DECISION_ALLOW),              # Windows cmd
    ("cat ", DECISION_ALLOW),             # Linux / Git Bash
    ("type ", DECISION_ALLOW),            # Windows cmd
    ("pwd", DECISION_ALLOW),              # Linux / Git Bash
    ("cd", DECISION_ALLOW),               # Windows cmd（pwd对应，cd跨平台）
    ("echo ", DECISION_ALLOW),            # 跨平台
    ("git status", DECISION_ALLOW),       # 跨平台git
]

class Registry:
	def __init__(self, *tools):
		self.tools = {}
		self.has_read = set()
		for t in tools:
			self.tools[t.definition()["name"]] = t
	
	def definitions(self):
		return [{"type": "function", "function": t.definition()} for t in self.tools.values()]
	
	def execute(self, name, args):
		t = self.tools.get(name)
		if t is None:
			return "Error: Unknown tool " + name
		if name in ("write_file", "edit_file"):
			path = path_of(args)
			if path and os.path.exists(path) and path not in self.has_read:
				return "Error: " + path + " exists but has not been read in this session. Use read_file first before modifying."
		if name == "bash":
			cmd = command_of(args)
			decision = classify_bash(cmd)
			if decision == DECISION_DENY:
				return "Error: Permission denied — This command matches a hard block rule. It will not be executed and no prompt will be shown."
			if decision == DECISION_ASK and not ask_approval(cmd):
				return "Error: Permission denied — The user has not approved this command."
		result = t.execute(args)
		path = path_of(args)
		if path and not result.startswith("Error"):
			self.has_read.add(path)
		return result

def command_of(args):
	try:
		return (json.loads(args) or {}).get("command", "") or ""
	except json.JSONDecodeError:
		return ""

def classify_bash(cmd):
	for pattern, decide in BASH_RULES:
		if decide == DECISION_DENY and pattern in cmd:
			return DECISION_DENY
	for pattern, decide in BASH_RULES:
		if decide == DECISION_ASK and pattern in cmd:
			return DECISION_ASK
	trimmed = cmd.lstrip(" \t")
	for pattern, decide in BASH_RULES:
		if decide != DECISION_ALLOW or pattern not in cmd:
			continue
		# if trimmed.startswith(pattern) and not contains_shell_chain(cmd):
		if trimmed.startswith(pattern):
			return DECISION_ALLOW
	return DECISION_ALLOW

def path_of(args):
	try:
		return (json.loads(args) or {}).get("path", "") or ""
	except json.JSONDecodeError:
		return ""

def contains_shell_chain(cmd):
	return any(ch in cmd for ch in ";|&$()`\n")

def ask_approval(cmd):
	print(f"\n Warning: The model tries to execute {cmd}\n Is it allowed?", end="", file=sys.stderr, flush=True)
	try:
		line = sys.stdin.readline()
	except OSError:
		return False
	if not line:
		return False
	answer = line.strip().lower()
	return answer in ("y", "yes")

from skill_layer import skill_manifest

# --- Memory ---

# The long-term cross-session memory maintained by 
# the model is persisted locally on the machine.

MEMORY_FILE = "MEMORY.md"

def read_memory():
	try:
		with open(MEMORY_FILE, encoding="utf-8") as f:
			return f.read().strip()
	except OSError:
		return ""

MEMORY_GUIDANCE = f"""
# Cross-Session Memory ({MEMORY_FILE})

`{MEMORY_FILE}` is a memory file maintained by yourself, not a draft for the current task.
After this task ends, in the next brand-new session — a completely fresh start instead of resuming this session with `-c` — the content you write now will be reloaded in the system prompt.

- Worth recording: Preferences explicitly requested by the user, project conventions differing from defaults, and verified conclusions likely to be reused later.
- Not worth recording: Intermediate states of the current task and specific code changes. Those are already tracked in files and Git history and do not need duplication here.

There is no dedicated tool for "remembering" or "forgetting". `{MEMORY_FILE}` is just an ordinary file:
- Use `write_file` to add new entries
- Use `edit_file` to modify or delete existing entries
Misremembering a fact is the same kind of operation as editing a line of code, using the same set of tools.

Before referencing content from this file, verify whether it still holds true — projects evolve, and previous notes are not guaranteed to remain valid."""

def compose_system_prompt(skills):
	manifest = skill_manifest(skills)
	prompt = "\n\n---\n\n" + MEMORY_GUIDANCE
	if manifest:
		prompt = "\n\n---\n\n" + manifest + prompt
	mem = read_memory()
	if mem:
		prompt += "\n\n## The past memory\n\n" + mem
	else:
		prompt += "\n\n## The past memory\n\n（Still empty, maybe it is the first time I meet with you）"
	return prompt
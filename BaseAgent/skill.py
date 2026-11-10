import os
import json

# --- Skill Layer ---

SKILLS_ROOT = ".harness-skills"

class Skill:
	def __init__(self, name, description, body, dir):
		self.name = name
		self.description = description
		self.body = body
		self.dir = dir

def discover_skills(skills_root=SKILLS_ROOT):
	out = {}
	try:
		entries = os.scandir(skills_root)
	except OSError:
		return out
	with entries:
		for entry in entries:
			if not entry.is_dir():
				continue
			try:
				with open(os.path.join(entry.path, "SKILL.md"), encoding="utf-8") as f:
					data = f.read()
			except OSError:
				continue
			desc, body, ok = parse_skill_file(data)
			if not ok or not desc:
				continue
			out[entry.name] = Skill(entry.name, desc, body, entry.path)
	return out

def parse_skill_file(text):
	lines = text.split("\n")
	if not lines or lines[0].strip() != "---":
		return "", "", False
	description = ""
	i = 1
	while i < len(lines):
		if lines[i].strip() == "---":
			break
		if ":" in lines[i]:
			key, _, val = lines[i].partition(":")
			if key.strip() == "description":
				description = val.strip()
		i += 1
	if i >= len(lines):
		return "", "", False
	body = "\n".join(lines[i + 1:]).strip()
	return description, body, True

def skill_manifest(skills):
	if not skills:
		return ""
	lines = ["# Available skill", "",
             "When a task matches a description, invoke the skill tool (parameter `name`) first to load the full instructions before taking any action."
             "— Do not guess the full content merely from this single description.", ""]
	for name in sorted(skills):
		lines.append(f"- {name}: {skills[name].description}")
	return "\n".join(lines).strip()  
	
class SkillTool:
	def __init__(self, skills):
		self.skills = skills

	def definition(self):
		return {
			"name": "skill",
			"description": "Load the full instructions of a skill. First check the 'Available Skills' list in the system prompt."
                           "When a task matches a description, use this tool to load the body of the corresponding skill before taking action.",
            "parameters": {
            	"type": "object",
            	"properties": {
            		"name": {"type": "string", "description": "The name of the skill to load; the word after the '-' in the list."},
            	},
            	"required": ["name"],
            },
		}

	def execute(self, args):
		try:
			params = json.loads(args)
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		name = params.get("name", "")
		sk = self.skills.get(name)
		if sk is None:
			return f"Error: No skill named {name} — select one from the list in the system prompt"
		return f'[skill "{sk.name}", is in the directory: {sk.dir}]\n\n{sk.body}'






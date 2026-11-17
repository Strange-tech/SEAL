import json
from subprocess_agent import run_layout_agent

task = open("/tmp/study_prompt.txt", encoding="utf-8").read().strip()
out = run_layout_agent(task, image_path=None)
print(json.dumps(out, ensure_ascii=False, indent=2))

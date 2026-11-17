import json
from pathlib import Path
from subprocess_agent import run_arti_agent, _node_box

SCENE = "/mnt/sda/johnli/SEAL/BaseAgent/output/layoutagent/4-0m-x-3-0m-z-2-8m-y-y-z-y-0-z-1-5-1-2m-1-2m-0-9-20261113-160721.json"
OUT = "/mnt/sda/johnli/SEAL/BaseAgent/output/artiagent/study__chair.json"

scene = json.loads(Path(SCENE).read_text(encoding="utf-8"))
chair = next(n for n in scene["nodes"] if n.get("id") == "chair")
box = _node_box(chair)
print("chair box:", box, flush=True)
out = run_arti_agent("office chair", image_path=None, box=box, emit_result=OUT)
print("ok:", out.get("ok"), flush=True)
print("result:", out.get("result"), flush=True)

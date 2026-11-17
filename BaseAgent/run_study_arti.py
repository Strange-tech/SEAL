import json
import sys
from pathlib import Path

from subprocess_agent import run_arti_agent, _node_box

SCENE = "/mnt/sda/johnli/SEAL/BaseAgent/output/layoutagent/4-0m-x-3-0m-z-2-8m-y-y-z-y-0-z-1-5-1-2m-1-2m-0-9-20261113-160721.json"
OUT_DIR = Path("/mnt/sda/johnli/SEAL/BaseAgent/output/artiagent")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Terse name-only task for each object; ArtiAgent's structurer expands it (text-only).
NAMES = {
    "desk": "desk",
    "chair": "office chair",
    "desk_lamp": "desk lamp",
    "laptop": "laptop",
    "bookshelf": "bookshelf",
    "dresser": "chest of drawers",
    "rug": "rug",
}

scene = json.loads(Path(SCENE).read_text(encoding="utf-8"))
objects = [n for n in scene.get("nodes", []) if n.get("type") == "object"]

results = []
for n in objects:
    nid = n["id"]
    name = NAMES.get(nid, nid)
    box = _node_box(n)
    emit = OUT_DIR / f"study__{nid}.json"
    print(f"==== {nid}  (task={name!r}, box={box}) ====", flush=True)
    out = run_arti_agent(name, image_path=None, box=box, emit_result=str(emit))
    ok = out.get("ok")
    res = out.get("result")
    results.append((nid, name, str(emit), ok, res))
    print(f"  -> ok={ok}  result={res}", flush=True)

print("\n=== SUMMARY ===", flush=True)
for nid, name, emit, ok, res in results:
    ad = (res or {}).get("asset_dir") if isinstance(res, dict) else None
    print(f"{nid:12s} ok={ok}  {emit}  asset={ad}", flush=True)

arti_paths = [str(OUT_DIR / f"study__{nid}.json") for nid, *_ in results]
print("\n=== ARTI LIST ===", flush=True)
print(json.dumps(arti_paths, indent=2, ensure_ascii=False), flush=True)

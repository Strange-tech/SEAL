#!/usr/bin/env bash
# BaseAgent end-to-end pipeline smoke test: reconstruct a room with the ten objects
# (the same set ArtiAgent / LayoutAgent use), exercising the full orchestration:
#   LayoutAgent (scene graph) -> per-object ArtiAgent (rest/swept bbox) -> feedback loop
#   (bake the measured swept bboxes back into the layout and re-validate for collisions).
# After the run, regenerates viewer_config.json to point at this run's outputs.
# Run from BaseAgent/test/ (or anywhere) with the `layout` conda env active.
# NOTE: do NOT run as-is unless you intend to launch the full LLM pipeline (expensive).
set -euo pipefail
cd "$(dirname "$0")/.."   # BaseAgent root

TASK="reconstruct a room with a wooden chair, a coffee table, a floor lamp, a desk computer, a ceramic mug, a glass bottle, a hardcover book, a chest of drawers, a flower vase, and a wall clock"

python main.py --task "$TASK"

# Auto-generate viewer_config.json pointing at this run's layout + arti results.
TASK="$TASK" python - <<'PY'
import json
import re
from pathlib import Path

BASE = Path.cwd()          # BaseAgent root (we cd'ed here above)
OUT = BASE / "output"


def _latest(pattern):
    files = list(OUT.glob(pattern))
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


# Latest refined scene graph (feedback loop output); fall back to the latest
# original scene graph (ignoring the _refined/_placements/_bboxes suffixes).
layout = _latest("layoutagent/*_refined.json")
if layout is None:
    originals = [p for p in OUT.glob("layoutagent/*.json")
                 if not any(s in p.name for s in ("_refined", "_placements", "_bboxes"))]
    layout = max(originals, key=lambda p: p.stat().st_mtime) if originals else None

placements = _latest("layoutagent/*_placements.json")

# Final scene: if placements exist (feedback loop ran), they already carry the asset
# poses, so leave `arti` empty; otherwise fall back to the raw arti results.
arti = []
if placements is None and layout is not None:
    prefix = re.sub(r"(_refined)?\.json$", "", layout.name)
    arti = sorted(p for p in OUT.glob(f"artiagent/{prefix}__*.json")
                  if not p.name.endswith(".placement.json"))

cfg = {
    "layout": str(layout.relative_to(BASE)) if layout else None,
    "placements": str(placements.relative_to(BASE)) if placements else None,
    "arti": [str(p.relative_to(BASE)) for p in arti],
}
(BASE / "viewer_config.json").write_text(
    json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(f"[viewer-config] layout={cfg['layout']}  placements={cfg['placements']}  arti={len(arti)}  -> viewer_config.json")
PY

# Ensure room_viewer is up (start it in the background only if it isn't already listening).
if curl -s -o /dev/null --max-time 2 http://127.0.0.1:8765/ 2>/dev/null; then
    echo "[viewer] already running on :8765 — refresh http://<服务器IP>:8765/"
else
    setsid nohup python3 room_viewer.py --config viewer_config.json --port 8765 \
        > /tmp/room_viewer.log 2>&1 < /dev/null &
    echo "[viewer] started on :8765 — open http://<服务器IP>:8765/"
fi

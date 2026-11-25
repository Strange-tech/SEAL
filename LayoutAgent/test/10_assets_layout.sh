#!/usr/bin/env bash
# LayoutAgent smoke test: reconstruct one room containing the same ten objects
# that ArtiAgent generates (see ArtiAgent/test/10_assets_only_text.sh).
# Run from LayoutAgent/test/ (or anywhere) with the `layout` conda env active.
# NOTE: do NOT run as-is unless you intend to launch one full LLM reconstruction.
set -euo pipefail
cd "$(dirname "$0")/.."   # LayoutAgent root (main.py / room.py live here)

python main.py --task "a room with a wooden chair, a round coffee table, a floor lamp, a desk lamp, a ceramic mug, a glass bottle, a hardcover book, a chest of drawers, a flower vase, and a wall clock" \
    --emit-scene-graph "output/10_assets_layout.json"

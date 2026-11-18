#!/usr/bin/env bash
# ArtiAgent smoke test: 10 simple single-object asset generation commands.
# Run from ArtiAgent/test/; each line runs one LLM generation.
# NOTE: do NOT run as-is unless you intend to launch 10 sequential generations.
set -euo pipefail
cd "$(dirname "$0")/.."   # ArtiAgent root (model.py lives here)

python main.py --provider deepseek --model deepseek-flash --task "a wooden chair"
python main.py --provider deepseek --model deepseek-flash --task "a round coffee table"
python main.py --provider deepseek --model deepseek-flash --task "a floor lamp"
python main.py --provider deepseek --model deepseek-flash --task "a desk lamp"
python main.py --provider deepseek --model deepseek-flash --task "a ceramic mug"
python main.py --provider deepseek --model deepseek-flash --task "a glass bottle"
python main.py --provider deepseek --model deepseek-flash --task "a hardcover book"
python main.py --provider deepseek --model deepseek-flash --task "a chest of drawers"
python main.py --provider deepseek --model deepseek-flash --task "a flower vase"
python main.py --provider deepseek --model deepseek-flash --task "a wall clock"

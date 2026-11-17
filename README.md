# SEAL — Scene Engine for Articulated Layout

**SEAL** is a hierarchical multi-agent system that reconstructs an indoor scene from a single
image and turns it into a layout of *articulated* 3D assets.

## Bug List

1. Layout朝向 用PCA估计太不准了
2. memory应该添加里程碑，避免重复调用工具
3. image指导的场景重建太不准了：遮挡物体幻觉，朝向，大小等很难调

## Agents

SEAL is three independent agents, each with its own system prompt, SDK, session, and file tree,
wired together by a subprocess contract (JSON in / JSON out):

| Agent | Role | Perception / geometry |
|-------|------|-----------------------|
| **BaseAgent** | Long-running orchestrator (REPL). Decides what to delegate and streams the sub-agents' logs back to the terminal. | DeepSeek (vision-capable) |
| **LayoutAgent** | Whole-image segmentation + room reconstruction → `room.py` scene graph (`nodes`/`edges`). | SAM3 (open-set segmentation), DA3 / Depth Anything 3 (metric depth) |
| **ArtiAgent** | Per-object generation of articulated assets (URDF + mesh) from an object mask + text description. | cadquery 2.7, manifold3d, python-fcl, trimesh |

```
┌──────────────────────────────────────────────────────────┐
│                       BaseAgent (REPL)                    │
│   read/write/edit tools · delegation rules · session     │
└──────────────┬───────────────────────────┬───────────────┘
               │ call_layout_agent          │ call_arti_agent
               ▼ (subprocess, JSON)         ▼ (subprocess, JSON)
┌──────────────────────────┐   ┌────────────────────────────┐
│       LayoutAgent        │   │         ArtiAgent          │
│  SAM3 seg → DA3 depth    │   │  mask + VLM → articulated  │
│  → room.py scene graph   │   │  asset (URDF + mesh)       │
└──────────────────────────┘   └────────────────────────────┘
```

## Directory layout

```
SEAL/
├── BaseAgent/     # orchestrator: REPL, subprocess delegation, output routing
│   └── agent/prompts/   # tools_instruction.md + system.md (routing rules)
├── LayoutAgent/   # SAM3 segmentation + DA3 reconstruction → room.py
│   ├── tools/     #   segmentation.py (SAM3), reconstruction.py (DA3), compile.py
│   └── sdk/       #   OBB / validation / projection / fitting / Manhattan
└── ArtiAgent/     # articulated asset generation (ex-articraft derived)
    └── sdk/       #   geometry SDK the LLM writes against (write-compile-fix loop)
```

## Current progress

| Phase | Goal | Status |
|-------|------|--------|
| 1 | BaseAgent long-running REPL (session persists across turns, `--image` support) | ✅ done |
| 2 | Subprocess orchestration layer + JSON contract (`--emit-scene-graph` / `--emit-result`) | ✅ done |
| 3 | ArtiAgent `--box` constraint + coordinate alignment | planned |
| 4 | ArtiAgent "real bounding box" tool (union over full joint range) | planned |
| 5 | BaseAgent main flow: layout first → per-box parallel ArtiAgent | planned |
| 6 | Bidirectional iterative optimization (real bbox → layout re-compile) | planned |
| 7 | Cross-object mutual adaptation (subtract/embeds, e.g. window cuts wall) | planned |
| 8 | Sub-agent session compression shared into BaseAgent | planned |

See `BaseAgent/EXECUTION_PLAN.md` and `BaseAgent/hierarchy_plan.md` for the full design spec.

## Requirements

- Linux server with CUDA GPU (SAM3/DA3 inference runs in bf16 autocast).
- Conda env `layout` (Python 3.10) with the dependencies of both sub-agents:
  LayoutAgent — SAM3 / depth-anything-3; ArtiAgent — cadquery 2.7, manifold3d, python-fcl,
  trimesh, networkx, zstandard (numpy 2.2.6).

### Model weights (kept outside this repo)

The large weights live under `$HOME` and are **not** committed:

- SAM3 checkpoint (~3.4 GB): `~/.cache/modelscope/models/facebook--sam3/snapshots/master/sam3.pt`
- DA3 weights: `~/models/DA3NESTED-GIANT-LARGE`

Override with environment variables where the defaults don't match your machine:

| Env var | Default | Used by |
|---------|---------|---------|
| `LAYOUT_PYTHON` | `/home/data/johnli/miniconda3/envs/layout/bin/python` | BaseAgent → LayoutAgent |
| `ARTI_PYTHON` | `/home/data/johnli/miniconda3/envs/layout/bin/python` | BaseAgent → ArtiAgent |
| `LAYOUT_AGENT_DIR` | `<SEAL>/LayoutAgent` (resolved next to BaseAgent) | BaseAgent |
| `ARTI_AGENT_DIR` | `<SEAL>/ArtiAgent` (resolved next to BaseAgent) | BaseAgent |
| `SAM3_CHECKPOINT` | modelscope cache `sam3.pt` | LayoutAgent |
| `DA3_MODEL` | `~/models/DA3NESTED-GIANT-LARGE` | LayoutAgent |
| `DA3_PROCESS_RES` | `1008` | LayoutAgent |

`LAYOUT_AGENT_DIR` / `ARTI_AGENT_DIR` now resolve relative to `BaseAgent`'s location, so the whole
`SEAL/` tree can be moved or renamed without breaking delegation.

## Quick start

```bash
cd SEAL/BaseAgent
# one-shot:
python main.py --image input/kitchen.png --task "reconstruct the kitchen"
# interactive REPL:
python main.py
```

Inside the REPL, `/image <path>` attaches an image for the next turn and `/help` lists commands.
Delegation rules (whole-image → LayoutAgent, per-object asset → ArtiAgent) live in
`BaseAgent/agent/prompts/tools_instruction.md`.

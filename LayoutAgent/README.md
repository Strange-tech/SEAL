# Layout-Agent

Reconstruct an indoor layout from a single-frame indoor image: input an image, output `room.py`
(scene-graph code: node = object OBB including walls/floors, edge = embedded / adjacent / abuts / allowed overlap).

The design idea comes from ex-articraft (Arti-Agent): use an SDK to simplify complex geometry into objects/functions the LLM can easily understand and write, and pair it with a compile tool that returns concrete error feedback, forming a "write-compile-fix" loop.

## Directory structure

```
layoutagent/
├── plan.md                    # design spec
├── schema.py                  # scene-graph data contract (node/edge types)
├── agent.py                   # main loop: perception + write-compile loop
├── sdk/                       # SDK: geometry / validation / backprojection / fitting / Manhattan regularization
│   ├── geometry.py            #   OBB primitives: rotation, corners, points->OBB, SAT intersection
│   ├── validation.py          #   relation-aware collision/floating detection (compile core)
│   ├── projection.py          #   depth + intrinsics + extrinsics -> world point cloud
│   ├── fitting.py             #   upright OBB fitting, RANSAC plane, floor/wall detection
│   └── manhattan.py           #   East/North orthogonal basis + orientation snap
├── tools/                     # perception + feedback tools (SAM3/DA3 lazy-loaded)
│   ├── segmentation.py        #   SAM3 open-set segmentation
│   ├── reconstruction.py      #   Depth Anything 3 reconstruction
│   ├── compile.py             #   run room.py -> validate -> diagnose
│   └── fileio.py              #   file read/write
├── prompts/                   # prompt engineering
│   ├── docs.md                #   SDK reference (must-read before the LLM writes room.py)
│   └── system_prompt.md       #   system prompt
└── tests/                     # all pure NumPy tests, no GPU needed
```

## Quick start

```bash
# run all tests (no GPU / no SAM3/DA3 needed)
python layoutagent/tests/run_all.py

# verify the package imports (should succeed even without GPU dependencies)
python -c "import layoutagent; print(layoutagent.__version__)"
```

The perception tools (SAM3 / DA3) need a CUDA GPU and are wrapped with lazy loading: when not installed,
`import layoutagent` still works, and it only errors when an inference method is actually called.

## Data contract (summary)

- node: `{"id", "type", "C": [x,y,z], "D": [w,h,l], "theta": [rx,ry,rz]}`,
  `type ∈ {wall, floor, door, window, object}`.
- edge: `{"type", "src", "dst"}`,
  `type ∈ {embedded_in, adjacent, abuts, overlaps_ok}`.
- The world frame is y-up; rotation `R = Rx·Ry·Rz` (degrees); indoor objects are upright `theta=[0, yaw, 0]`.

The full contract, validation rules, and exemptions are in `prompts/docs.md`.

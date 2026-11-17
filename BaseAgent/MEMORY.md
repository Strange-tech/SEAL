# MEMORY

## User preferences / conventions
- The user frequently requests **layout-only** generations (no 3D assets) and often **without any attached image** — e.g. "generate a room layout with U shape", "L shape", "square room with sofa/TV/table/chairs/windows/doors/bicycle".
  - In those cases: call `call_layout_agent` only, pass a short task (<=8 words), and **omit** `image_path` (text mode). Do not browse `input/` for an image.
  - Layouts go to `BaseAgent/output/layoutagent/*.json`; report the output path plus a brief node/edge summary.

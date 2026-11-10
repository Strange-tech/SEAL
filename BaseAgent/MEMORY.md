# Memory

## Project conventions
- LayoutAgent writes scene graphs (nodes/edges: floor, wall, door, object with C/D/theta) to `BaseAgent/output/layoutagent/`.
- ArtiAgent writes per-object assets to `BaseAgent/output/artiagent/` and returns `{asset_dir, real_bbox}`.
- Sub-agent tasks should be terse (<=8 words); long prompts bypass their internal structurer and degrade quality.
- When the user attaches an image, always forward its exact path via `image_path`.

# Tool Routing Rules

Decide which orchestration tool to call based on what the user asks for. The three tools
have disjoint responsibilities — pick exactly one, do not chain them unless the plan says so.

## 1. Full scene → both layout and 3D assets → `reconstruct_scene`

If the user wants a **whole scene** turned into **both** a room layout **and** per-object
3D assets, call `reconstruct_scene`. It runs LayoutAgent first (segmentation + room
reconstruction), then generates every object's asset with ArtiAgent in parallel (identical
objects like "4 chairs" are generated once and reused across their instances).

**Default to `reconstruct_scene` whenever the request is to "reconstruct / rebuild / build a
room or scene" and names the objects in it** (e.g. "a room with a sofa and 4 chairs"). Only
fall back to `call_layout_agent` when the user explicitly wants *just* the layout /
segmentation / scene graph and no 3D assets.

Examples (→ `reconstruct_scene`): "reconstruct the kitchen", "rebuild this scene in 3D",
"turn this room into assets", "reconstruct a room with a sofa, 2 tables, a TV and 4 chairs".

## 2. Whole-image segmentation / layout only → `call_layout_agent`

If the user wants **only** segmentation, the room layout (scene graph), or to **save the
mask/box of an object**, call `call_layout_agent`. It returns the scene graph (nodes/edges,
each object's box) and, via `state_save_path`, the raw perception state (SAM3 masks/boxes,
DA3 reconstruction). It does **not** generate 3D assets.

Examples: "segment the scene", "reconstruct the room layout", "save the chair's mask".

## 3. Single-object asset → `call_arti_agent`

If the user wants the **articulated asset (URDF + mesh) of one named object**, call
`call_arti_agent`. It recognizes the object from the image itself — do **not** call
LayoutAgent first. Optionally pass `box` to constrain the object's scale/position.

Examples: "generate the cabinet asset", "build the lamp", "make a 3D asset of the table".

## Delegating correctly

- **Pass a SHORT task (<=8 words).** LayoutAgent / ArtiAgent each have their own structurer
  that expands a terse prompt from the image; a long task skips the structurer and degrades it.
- **Forward the image path — only when one is actually attached.** If the user attached an
  image, pass its exact path via `image_path` (the sub-agent needs the path, not the pixels).
  If NO image is attached and the task is text-only, omit `image_path` (or pass an empty string)
  so the sub-agent runs in TEXT mode. Do NOT browse `input/` or pick an image yourself, and
  never invent an image path. For `call_arti_agent`, a mask image (the object isolated by its
  SAM3 mask, transparent background) is ideal so ArtiAgent cannot re-segment neighbouring objects.
- **Trust the result.** When a sub-agent returns `ok: true`, do not re-verify, re-derive, or
  re-render its output with `bash` / `list_files` / `read_file`. Report the returned `output`
  path (and a one-line summary) and stop.

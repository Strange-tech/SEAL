# Layout SDK Quickstart

## Purpose

Use this page to start a new layout reconstruction script. It defines the
required script contract, the authoring workspace rules, and one minimal
end-to-end example that turns a single indoor image into a validated scene
graph. Detailed validation rules live in the mounted `docs/sdk/references/testing.md`.

## Virtual Workspace

You are editing a virtual authoring workspace.

- `room.py` is the only writable file.
- `docs/sdk/references/quickstart.md` is this always-loaded entrypoint.
- Everything under `docs/sdk/references/` is read-only SDK guidance.
- `room.py` is self-contained: it defines `build_scene_graph()` and returns
  plain Python dicts; no imports are required.
- Use `read_file(path=...)` to load exact reference text only when needed.

## Mounted Reference Layout

- `docs/sdk/references/quickstart.md`: script contract, workspace rules, minimal example, workflow.
- `docs/sdk/references/testing.md`: the three diagnostic tiers and every validation exemption.
- `docs/sdk/references/walls_and_floor.md`: the rules for walls and floor. If the task mentions room shape / walls / floor (e.g. square, L-shape, U-shape, alcove, partition), you MUST read it before writing room.py.

Read the exact document you need. Do not guess field names or types from memory.

## Script Contract

Every generated script must define:

- `build_scene_graph() -> dict`

It returns a scene graph with two lists:

```python
def build_scene_graph():
    return {
        "nodes": [...],
        "edges": [...],
    }
```

`compile` executes `room.py`, calls `build_scene_graph()`, validates the
result, and reports three tiers: `failure`, `warning`, `note`. Drive all three
to zero.

## Scene Graph Data Contract

A node is one object's oriented bounding box (OBB), including walls and floors:

```python
{"id": "floor", "type": "floor", "C": [x, y, z], "D": [w, h, l], "theta": [rx, ry, rz]}
```

- `id`: unique non-empty string.
- `type`: exactly one of `wall`, `floor`, `door`, `window`, `object`.
- `C`: OBB center `[x, y, z]` in meters.
- `D`: OBB extents `[w, h, l]` along the local x/y/z axes (non-negative).
- `theta`: Euler angles `[rx, ry, rz]` in degrees.

An edge is a spatial relation between two nodes:

```python
{"type": "embedded_in", "src": "door_0", "dst": "wall_0"}
```

- `type`: exactly one of `embedded_in`, `adjacent`, `supports`, `overlaps_ok`.
- `src`, `dst`: existing node ids; the relation is directed `src -> dst`.

Only include objects that are visible in the image. Do not write hidden or
occluded objects.

## Coordinate System

- COORDINATE FRAME (critical): `room.py` must use a right-handed y-up room frame — +x right,
  +y up, +z TOWARD the camera; the reference horizontal surface (the LARGEST horizontal plane in 
  the shot: the floor in a wide shot, the countertop/tabletop in a close-up) has its TOP at y=0, 
  and the back wall (farthest wall) is at z=0. Reconstruct ONLY what is actually visible: if the 
  floor is not in frame, do NOT declare a `floor` node — put the countertop/tabletop at y=0 
  instead. `da3_reconstruct`/`backproject_obb` give a camera frame (x right / y down / z forward,
  camera at origin): convert with `room = [cam_x, -cam_y + h, -cam_z + D]`, where h is the camera 
  height above the reference surface and D is the camera-to-back-wall distance (read both from the 
  backprojected surfaces). NOTE: this flip is exact only for a LEVEL camera; if the camera is 
  pitched or rolled, the SDK's alignment routine (`estimate_room_transform`, run automatically 
  during validation) performs the exact pitch/roll correction — so keep the room frame 
  image-anchored and let validation align it. Flip y and z signs and normalize the reference 
  surface top to 0 and the back wall to 0.
- Rotation is `R = Rx(rx) @ Ry(ry) @ Rz(rz)`, all angles in degrees.
- `D = [w, h, l]` maps to the local x/y/z axes, so `h` is the vertical extent.
- Metric scale: DA3 depth is a learned metric prior, not an exact measurement. Use
  its backprojected OBB scale as the base for each object's `D`, cross-check it
  against your own size estimate from the image, and if a backprojected OBB has a
  clearly wrong scale (e.g. a contaminated mask), correct it with your knowledge of
  real-world object sizes.
- Indoor objects are upright: `theta = [0, yaw, 0]`, with `rx = rz = 0`; only
  the yaw `ry` is meaningful.
  - A wall running along x has `theta = [0, 0, 0]`; a wall along z has
    `theta = [0, 90, 0]`.
  - **Wall facing convention**: a wall's normal is its local +Z (thickness)
    axis, and **+Z must point indoors (inward normal)**. For a given wall there
    are two legal yaws 180° apart — pick the one that makes +Z face into the room.
    Example: a wall running along x with the room on its +z side has
    `theta = [0, 0, 0]`; if the room is on its -z side, use `theta = [0, 180, 0]`.
    Walls running along z are analogous with ±90.

## Relations

| relation | semantics | exemption |
|----------|-----------|-----------|
| `embedded_in` | a door/window embedded in a wall | intersection legal (no collision) |
| `adjacent` | horizontal adjacency; a small gap is allowed | none |
| `supports` | `src` is supported by `dst` (a cup on a table, a picture on a wall); OBB faces in tight contact | `src` exempt from floating check |
| `overlaps_ok` | OBBs intersect but legal (a chair under a table) | intersection legal; warning if they do not actually intersect |

## Minimal Example

```python
def build_scene_graph():
    return {
        "nodes": [
            {"id": "floor", "type": "floor", "C": [2.0, -0.05, 2.0], "D": [4.0, 0.1, 4.0], "theta": [0, 0, 0]},
            {"id": "wall", "type": "wall", "C": [2.0, 1.2, 0.0], "D": [4.0, 2.4, 0.16], "theta": [0, 0, 0]},
            {"id": "window", "type": "window", "C": [2.0, 1.3, 0.0], "D": [1.2, 1.0, 0.16], "theta": [0, 0, 0]},
            {"id": "table", "type": "object", "C": [1.5, 0.375, 1.5], "D": [1.2, 0.75, 0.8], "theta": [0, 0, 0]},
            {"id": "chair", "type": "object", "C": [1.5, 0.25, 1.5], "D": [0.45, 0.5, 0.45], "theta": [0, 0, 0]},
        ],
        "edges": [
            {"type": "embedded_in", "src": "window", "dst": "wall"},
            {"type": "overlaps_ok", "src": "chair", "dst": "table"},
        ],
    }
```

The floor is a thin box (`D = [w, 0.1, l]`) centered slightly below zero
(`y = -0.05`) so its top is exactly at `y = 0`. The wall is a thin box about
`0.16` thick with room-height vertical extent. The window sits inside the wall
and is linked with `embedded_in`. The chair is tucked under the table, so the
two are linked with `overlaps_ok`. Every `object` and `wall` has its bottom at
`C[1] - D[1]/2 = 0`, resting on the floor.

## Recommended Workflow

1. Describe the visible objects in the image (VLM auxiliary).
2. Run `sam3_segment` per object name to get each object's mask.
3. Run `da3_reconstruct` to get metric depth plus camera intrinsics/extrinsics.
4. Backproject each mask and fit an upright OBB with `backproject_obb`.
5. Detect the floor and walls, then `manhattan_regularize` orientations.
6. Write `build_scene_graph()` in `room.py`.
7. Run `compile` and repair every `failure`/`warning`/`note`.

## Layout Brief

Before coding, translate the image into a short internal Layout brief. Do not
ask the user to provide this structure. Use it to make the first pass coherent
and to choose what to reconstruct, not just to make the graph compile.

```text
Layout brief:
- Scene: room identity and approximate real-world scale.
- Structure: the floor and walls that carry the room.
- Objects: visible objects and their rough placement.
- Relations: primary embedded_in/adjacent/supports/overlaps_ok edges.
- Assumptions: meaningful inferred choices.
```

## Authoring Habits

- Write the floor first: a thin box, `type="floor"`, `D=[w, 0.1, l]`, centered
  at `y = -0.05`.
- Write walls as thin boxes about `0.16` thick with room-height vertical extent.
- Put door/window nodes into their wall and add an `embedded_in` edge to it.
- Write furniture as `object` with its bottom on the ground (`C[1] = D[1]/2`).
- Add `adjacent`/`supports`/`overlaps_ok` edges only where the relation is real.
- After writing, self-check that every non-floor object sits on the floor and
  no unintended collision remains.


# Memory

## Workspace / path conventions (verified 2026-11)

- The shell cwd for tool calls is `/home/data/johnli/BaseAgent`, NOT the repo root of
  LayoutAgent/ArtiAgent. Each agent tool (`call_layout_agent`, `call_arti_agent`) runs
  in its own cwd: `/mnt/sda/johnli/LayoutAgent` and `/mnt/sda/johnli/ArtiAgent`.
  Relative `emit_scene_graph` / `emit_result` paths land under THAT agent's `output/`.
- `call_arti_agent(image_path=...)` resolves relative paths against ArtiAgent's cwd, so
  images that live in `/mnt/sda/johnli/LayoutAgent/input/` must be passed absolute, or
  omitted. Reference images attached by the user in chat are NOT on disk.
- ArtiAgent's emitted result JSON often has `real_bbox: null` and `asset_dir` pointing at
  `data/records/<record_id>`. The actual buildable artifacts (model.urdf + per-visual
  OBJ meshes under `assets/meshes/`) live in
  `data/cache/record_materialization/<record_id>/`. Read `record.json` for the id.
- No headless GL renderer available (pyglet/pyrender missing in this env). To eyeball a
  model, render OBJs with matplotlib `Poly3DCollection` — remember to scale mesh units
  to mm to match the axis limits, otherwise the figure comes out blank.

## Articraft / CadQuery environment quirks (verified 2026-11)

- `Workplane(...).rect(w,h).vertices().fillet(r)` FAILS in this env with
  "Cannot find a solid on the stack". Use a 2D `cq.Sketch().rect(w,h).vertices().fillet(r)`
  then `Workplane(plane).center(x,z).placeSketch(sk)`, or `slot2D` for capsules.
- Filleting an extruded prism's corner edges (`edges("|Y").fillet(r)`) only works
  when the extrusion depth is comfortably larger than `2*r`; thin plates must be
  rounded in the sketch instead.
- A second `.fillet()` in the same Workplane chain (e.g. front then back perimeter)
  fails. Select both ends' edges in ONE call: collect edges via
  `wp.edges().vals()` filtered by `abs(e.Center().y)`, then
  `wp.newObject(edges).fillet(r)`.
- `cq.selectors.UnionSelector` does NOT exist in this cadquery build.
- Text on the +Y face: build with `Workplane("XZ").text(..., fontsize=..., distance=..., combine=False)`
  (reads correctly from -Y, extrudes toward -Y) then
  `rotate((x,0,z),(x,0,z+1),180)` — a proper rotation, so no mirroring — then
  translate to the front surface. Verified via geometry AABB, avoids the
  XZ-mirror trap.
- Compiler QC requires every part to touch the grounded root geometrically:
  captive buttons in clearance bores / detached display props get flagged as
  "floating". Use `ctx.allow_isolated_part(part, reason=...)` (plus proof checks)
  for clearance-mounted controls and intentionally detached objects.
- FIXED/REVOLUTE articulations do NOT satisfy that geometric support check (it is
  distance-based, tol 1e-6). Make mating parts touch exactly (zero gap), or they
  are reported as disconnected from the grounded group.
- The compiler "real 3D overlap" pass behaves like an AABB check: reported
  `depth`/`vol` equal the per-axis box-overlap extents and their product. Two
  diagonal articulated links crossing around a shared pivot always trip it; fix
  with element-scoped `ctx.allow_overlap(...)` plus `expect_contact` proofs
  instead of distorting the geometry.
- `ctx.allow_overlap(a, b, elem_a="x", elem_b=None)` does NOT suppress a reported
  overlap: an element-scoped allowance only matches when BOTH elems are named
  (or both are None = part-level). Verified: hanger/barrel+stem overlaps kept
  failing until the allowance was made part-level.
- Overlap/contact QC uses `overlap_tol=0.005` on the min per-axis depth, so joints
  must be fully face-flush (zero depth) to avoid an allowance; real bolted joints
  that embed a few mm always need an explicit allowance + a proof check.
- `LoftGeometry` fails on tilted (non-XY-planar) section loops; for sweeps along a
  curved path generate the mesh yourself (ring quads + centroid-fan end caps) and
  wrap it with `mesh_from_geometry`.
- `tube_from_spline_points(...).radial_segments` must be >= 6.

- Validation requires EXACTLY ONE root part. Multi-piece scenes (e.g. chair +
  free-standing ottoman) fail with "must have exactly one root part". Fix: parent
  the second assembly to the first with a `FIXED` articulation whose origin is the
  assembly's placement offset (author that child's geometry in its own local
  frame), then `ctx.allow_isolated_part(...)` for every part of the detached group
  (the floating-group pass is geometric, so FIXED joints do not satisfy it).
- Double-curved shells/cushions: hand-built parametric grid meshes work well and
  avoid loft pitfalls — sample top/bot `f(a,b)` grids, emit quads for each
  surface plus rim quads around the boundary, wrap with `mesh_from_geometry`.
  Squircle mapping `nx*r`-style rounds the footprint corners; gaussian dips in the
  top surface give button tufting for free.
- `mesh_from_cadquery` of a lone `Solid.makeCylinder` whose `dir` is not
  axis-aligned exports at the wrong location (its Location is not baked). Build
  such tilted cylinders as `CylinderGeometry(...)` +
  `MeshGeometry.rotate_*`/`translate`, or fuse them into a bigger solid.
  Axis-aligned cq cylinders export correctly.

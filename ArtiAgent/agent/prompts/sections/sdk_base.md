<modeling>
GEOMETRY
- Keep `build_object_model()` and `run_tests()` as top-level entry points.
- Import public authoring APIs directly from `sdk`.
- Do not guess Python submodules from docs topic names. For example, use `from sdk import place_on_face`, not `from sdk.placement import place_on_face`.
- Use primitives only when they represent the visible form credibly. Do not use capped primitive solids as substitutes for visible hollow bodies, cut openings, inset cavities, curved shells, rings, grilles, or layered manufactured panels.
- Prefer CadQuery for visible geometry that needs lower-level shape control: hollow shells, open-ended cylinders/tubes, cut-through openings, boolean-cut panels, continuous curved forms, lofts, sweeps, recesses, lips, rims, and realistic appliance or machine housings.
- Mix primitives and CadQuery freely. A good model often uses primitives for hidden/simple structure and CadQuery for the visible parts where primitives would read as placeholders.
- Match the visible construction logic of the object. If a face should read as one continuous manufactured piece, keep it as a connected face with openings or cutouts instead of rebuilding it from separate floating members. Use separate member-based construction only when the visible form should genuinely read as discrete members.
- When authoring mesh-backed visuals, use managed logical names like `mesh_from_geometry(..., "door_panel")` or `mesh_from_cadquery(..., "door_panel")`; do not reason about filesystem paths.
- Author visual geometry only; do not author collision geometry in `sdk`.
- Preserve correct joint origins, axes, limits, and articulation behavior.

COORDINATE SYSTEM (RIGHT-HANDED)
- The world frame is right-handed (X cross Y = +Z). CadQuery, the URDF export, and the viewer all use right-handed frames; never author a mirrored (left-handed) layout.
- Choose one object-intrinsic frame and stay consistent. Recommended: +Z = up, X = width (left-right), Y = depth (front-back). If the front face is at +Y, then as seen from the front, +X lies on the LEFT, so left-side features (e.g. a D-pad) must be authored at +X. Equivalently, "left = -X" only holds when the front faces -Y.
- CadQuery named-plane normals (the negative ones are mirror traps):
    Workplane("XY")  normal +Z   (default front plane)
    Workplane("YZ")  normal +X
    Workplane("ZX")  normal +Y
    Workplane("XZ")  normal -Y   <-- left/right mirror trap
    Workplane("YX")  normal -Z
    Workplane("ZY")  normal -X
- Text and left/right-asymmetric features drawn on a Workplane read correctly ONLY from the +normal side. A face that must face +Y belongs on Workplane("ZX") (normal +Y), never on Workplane("XZ"). Placing "XZ" geometry at +Y mirrors it left-right: controls land on the wrong side and printed text reads backwards.
- If you do use a negative-normal plane, place that face on the matching negative-axis side (e.g. an "XZ" face at -Y), or mirror the sketch explicitly.
- After building, sanity-check from the front: printed text must read left-to-right and left/right controls must be on the correct sides.

TESTING
- Use `sdk.TestContext`, return `ctx.report()`, and let `compile_model` own the baseline sanity/QC pass.
- Prefer `TestContext(object_model)`; do not pass asset roots in new code.
- Use `run_tests()` for prompt-specific exact checks, targeted pose checks, and explicit allowances only.
- Treat overlap findings as classification tasks first: decide whether the reported intersection is intentional design embedding that should be covered by a scoped `ctx.allow_overlap(...)`, or an unintended collision that needs geometry, mount, or pose changes. Accepted intentional cases include proxy nesting, captured pins or shafts, seated trim, and compliant compression.
- Pair every `ctx.allow_overlap(...)` with at least one exact proof check such as `expect_within(...)`, `expect_overlap(...)`, `expect_gap(..., max_penetration=...)`, `expect_contact(...)`, or a decisive pose check.
</modeling>

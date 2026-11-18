# Memory

## Part nested in a cup/mesh AABB reads as overlap even on flush seat (verified 2026-11, wall clock)

- A small part (movement housing cylinder) sitting on the interior back plate of a
  hollow case mesh (cup) is reported by `real_overlap` with
  `depth=(dx,dy,dz)=part's OWN full dims` (e.g. 0.06,0.06,0.0195 for a 0.06x0.06x0.0195
  part) — because the part nests fully inside the case's *AABB* in x/y/z, so the AABB
  min-depth = the part's whole extent, and `fcl.collide` returns true on the flush
  face contact. This is a proxy artifact, not a real embedding. Fix with element-scoped
  `ctx.allow_overlap(case, movement, elem_a="case_shell", elem_b="movement_body", reason=...)`
  + an `expect_contact(...)` proof. `pair_report` confirms `collided:true, min_distance:0`.
- Flush face contact where the parts DON'T nest in AABB (e.g. hand hub bottom coincident
  with dial front, z-overlap extent exactly 0) is NOT flagged by the compiler (probe
  `pair_report.collided` may still say true) — only actually-nested parts trip QC.
- cq text recipe re-verified: `Workplane("XY").text(s, fontsize=, distance=,
  combine=False, halign="center", valign="center").rotate((0,0,0),(0,1,1),180)` on the
  XY plane makes glyph advance->world +x, up->world +y, extrude->world +z (front), so
  it reads upright and unmirrored from the +z front. To ENGRAVE into a dial, place the
  glyph base at the dial front minus relief depth and `dial.cut(glyph)`; the recessed
  pockets ARE the readable digit (cutting a correctly-oriented glyph keeps it legible).
  Numerals upright (no per-position rotation) is correct for a clock. Placing world
  point (X,Y,Zf): translate the rotated glyph by cq `(-X, Zf, Y)` (mapping cq(x,y,z)->
  world(-x,z,y)).

## Hand-rolled y-up revolve + MeshGeometry API (verified 2026-02, glazed vase)

- `sdk.MeshGeometry.add_vertex(x, y, z)` takes THREE FLOATS (not a tuple);
  `add_face(a, b, c)` accepts only TRIANGLES (no quad arity) — split every quad
  into `(a,b,c)` + `(a,c,d)`. Passing a tuple/4-index face fails at runtime.
- Profile-in-(r,y) revolve directly in the y-up world frame (no cq, no axis
  conversion): vertex `(r sinθ, y, r cosθ)`, θ = 2πj/segments; emit lateral
  quads `(a_j, a_j2, b_j2, b_j)` for profile edge i->i+1 and normals come out
  of the material everywhere (verified: outer wall +radial, rim +y, underside
  -y, inner floor +y). r==0 points collapse to one apex vertex; the
  apex/b>0 edge becomes triangle `(apex, b_j2, b_j)`, apex/a>0 edge becomes
  `(a_j, a_j2, apex)`.
- Closed CCW (r,y) loop for a hollow open vessel: underside centre -> foot ring
  -> outer wall up -> over the rim -> inner wall down -> inner floor -> axis.
  `geometry_connectivity_report` confirmed one connected shell, no islands, so
  a single visual/part is a clean watertight vessel with real wall thickness.

## cq.Workplane.text orientation onto world faces (verified 2026-11, hardcover book)

- Confirmed again this build: `mesh_from_cadquery` maps cq->world as `world=(-cq_x, cq_z, cq_y)`
  (det +1). Invert: to hit world/local point `(X,Y,Z)`, author at cq `(-X, Z, Y)`.
- `cq.Workplane("XY").text(txt, fontsize=, distance=, combine=False, halign="center",
  valign="center")` makes glyphs advancing +x, up +y, extruded +z. Rotate the whole WP to
  orient it, then translate by `cq_target - bbox_center`:
  - Text on a **+Z front face** (advance->world +x, up->world +y, normal out->world +z):
    `.rotate((0,0,0),(0,1,1),180)`. Verified reads correctly via ASCII front-view raster.
  - Text on a **-X spine face** (advance->world -y top-to-bottom, up->world +z,
    normal out->world -x): `.rotate((0,0,0),(0,1,0),90)`. Verified not mirrored.
- Self-check without a renderer: parse the shipped OBJ (local-frame coords for meshes),
  take triangles in the *proud* slab (past the substrate face), project the two in-plane
  axes and draw a barycentric ASCII fill — legible enough to read "AUTHOR NAME"/"PUBLISHER".
- Union the extruded text into the board solid (`board.union(text.val())`) after sinking the
  text ~0.5-0.7 mm into it; overlapping solids let OCC union merge so the part is one
  connected mesh (no disconnected-geometry warning) and letters read as embossed relief.

## Hand-rolled lathe revolve + stroke-font lettering (verified 2026-02, glass bottle)

- Reliable hollow-vessel revolve with no cq: closed CCW `(r, y)` profile (material on
  the left: up the outside, in over the rim, down the bore, out along the inner floor),
  mapping `x = r*sin(th), z = r*cos(th)`, `theta = 2*pi*j/segments`, and lateral quads
  emitted as `(a_j, a_j2, b_j2, b_j)` (a = profile point i, b = i+1) -> outward normals.
  Points with `r == 0` collapse to one apex vertex and become triangles; skip segments
  where both ends are on the axis. Verified by re-parsing the shipped OBJ and checking
  the radius profile per y slice.
- A per-theta radius modulation applied only where `r >= r_min` gives knurled/fluted
  side walls on the same revolve (use segments = 4*flute_count).
- Moulded lettering without cq: a stroke font (polylines per glyph) extruded as thin
  rectangular prisms between a proud layer and an embedded layer, mapped onto the
  curved surface by `theta = u / R` (front text) or `r = r_mid + v` (base annulus text).
  Corner order must be CCW in the (u, v) plane; then outer face `(O0,O1,O2,O3)`, inner
  `(I0,I3,I2,I1)`, sides `(O_{k+1}, O_k, I_k, I_{k+1})` all come out outward. Embed the
  inner layer only ~0.9 mm so the radial overlap stays under the 5 mm overlap tol.
  Stroke width must be < ~35% of the char cell or lowercase counters fill in solid —
  render the shipped OBJ (barycentric triangle fill, ~40 lines of python) to check.
- A screw cap that wraps the neck always trips `real_overlap`: the skirt descends past
  the lip, so the two ELEMENT AABBs overlap ~16 mm in the axial axis while the solids
  only share the seat plane. Coincident seating faces are still reported, so use
  element-scoped `ctx.allow_overlap(bottle, cap, elem_a="bottle_body",
  elem_b="cap_shell", reason=...)` + `expect_contact`/`expect_overlap` proofs.
- No helical/screw articulation exists (only REVOLUTE/CONTINUOUS/PRISMATIC/FIXED/
  FLOATING), and two joints on one child form an invalid loop, so a threaded cap must
  be modelled as one joint: REVOLUTE about the neck axis (visible knurl spin) or
  PRISMATIC (lift-off). Pick one and say which motion is represented.

## CadQuery text lettering via mesh_from_cadquery (verified 2026-11, desk lamp)

- `cq.Workplane("XY").text(s, fontsize, distance, combine=False)` then
  `mesh_from_cadquery(shape, unique_name)` works and compiles clean. Font
  default Arial is present.
- Reading-direction fix under the (-x,z,y) OBJ mapping: a TOP-facing label
  (normal -> world +Y) needs `.rotate((0,0,0),(0,0,1),180)` to cancel the x
  flip; an UNDERSIDE label (must face world -Y) needs
  `.rotate((0,0,0),(0,1,0),180)`.
- Each line of text is SEPARATE letter islands, so a text strip must INTERSECT
  its substrate (e.g. sink the base 0.3 mm into the plate) or the compiler
  `disconnected_geometry` warning fires. Place flat labels on a truly flat
  surface; a tilted rocker top makes flat text partially float -> warning.

## Hinge-cover overlaps: allowance element names must match the compile report (verified 2026-11, desk lamp)

- The overlap QC reports the WORST per part-pair element pair only; iterating
  compile fixes one pair at a time. The cover cylinder vs the parent often
  reports `parent_dome`/`parent_post` rather than the intended post, so read the
  exact `elem_a`/`elem_b` names from the failure and mirror them in
  `ctx.allow_overlap(link_of_a, link_of_b, elem_a=<a-elem>, elem_b=<b-elem>)`
  (note link order: elem_a belongs to the FIRST link).
- A tilted cone/shade's AABB is huge, so it "overlaps" an adjacent arm's AABB
  massively even though the solids only touch at the pivot — this is a proxy
  artifact; allow it scoped to `shade_cone`/`upper_tube` with an
  `expect_contact` proof, don't reshape.
- `fit_to_box` was NOT used; with the authored AABB bounded the compile is clean.

## mesh_from_cadquery cq->world axis mapping is (-x, z, y) in this build (verified 2026-12, floor lamp)

- Measured from world AABBs + the materialized OBJs: a cq shape authored at (x,y,z)
  lands at world (-x, z, y). Determinant +1 (a 180 deg rotation about (0,1,1)), so
  normals survive, but BOTH a y/z swap and an x flip bite:
  - cq `z` is world UP (+y) as documented, but cq `+y` is world FRONT (+z) — put front
    features (bosses, knobs, text plates) at cq **+y**, not -y.
  - Anything x-asymmetric (pointer tabs, off-centre features) mirrors.
- Engraved text that must read from the world front: `Workplane("XZ").text(...)` (reads
  correctly from cq -Y, extrudes toward -Y), then `.rotate((0,0,0),(0,0,1),180)`, then
  translate to the boss front at cq +y minus the engraving depth. The 180 deg rotation
  cancels the OBJ x-flip, so the final world text reads left-to-right.
- Diagnosing part placement: the exported OBJs under `.compile_tmp/assets/meshes/` hold
  the mesh in the PART-local frame (visual origin NOT baked). world = part_frame +
  visual_origin + obj coords. A quick painter's-algorithm front-view ASCII render with
  those per-part baselines is enough to catch a whole-object misplacement.
- Pitfall that cost a compile cycle: authoring geometry in the joint-local frame
  (cq z = 0 at the joint origin) but ALSO passing that same joint origin as the visual
  origin double-offsets the part by exactly one joint height (and inflates fit/unions).

## AABB overlap proxy vs tapered / raked members (verified 2026-12, wooden chair)

- Compiler `real_overlap` measures per-ELEMENT AABB intersection. A leg that tapers
  over its whole length has an AABB fatter than its real section at stretcher height,
  so a 2 mm tenon embed reported 5.4 mm and failed (tol 5 mm). Fix: keep the section
  CONSTANT from the seat down past the stretcher and taper only below it (classic
  leg) — then depth == the true embed.
- Any part rotated about an axis inflates its AABB along the other two axes, so a
  raked post vs anything spanning it reads as a big overlap even with a 1.5 mm joint.
  Two remedies that both worked: (1) split the raked member into a vertical lower leg
  + a raked upper post, both ending flush at the seat; (2) put the panel BETWEEN the
  posts so the x-footprint overlap is only the 1 mm jointing embed.
- Winding that gave outward normals for "stack CCW loops in local (u,v) along +w":
  side quads `(a_j, a_j2, b_j2, b_j)` + `(a_j, b_j2, b_j)`, top cap fan
  `(c, p_j, p_j2)`, bottom cap `(c, p_j2, p_j)`. Any to_world map with det +1
  (e.g. `(u, w, -v)`) keeps them outward — verified via ASCII silhouette renders.
- No numpy/renderer needed to eyeball: a ~60-line painter-sorted ASCII rasterizer over
  `.compile_tmp/assets/meshes/*.obj` (project two axes, barycentric fill, ASCII chars
  are ~1:2 so use sx = 2*sy) is enough to confirm silhouette/proportions.

## Hand-built upholstered slab (verified 2026-12, sofa)

- Reliable soft-cushion mesh with NO cq/loft API: stack rounded-rect LOOPS at
  increasing height, where the inset of each ring follows a quarter circle
  (`inset = re*(1-cos t)`, `z = -h/2 + re - re*sin t` at the bottom, mirrored at the
  top). Each ring uses the same point count (`4*(seg+1)` from 4 quarter arcs), so
  side quads `(i,j),(i,j2),(i+1,j2),(i+1,j)` plus centroid fans for the two caps make
  one closed part. Gives rounded footprint corners AND rounded top/bottom rims, i.e.
  a real foam-cushion silhouette, and flat caps that seat exactly on neighbouring
  parts (contact QC passes with gap 0).
- Fixed-joint-only objects still satisfy the support QC as long as each part's
  geometry *touches* something exactly (contact graph), so a back cushion resting on
  a seat cushion which rests on the frame is fine.

## Current build's real_overlap rule (verified 2026-12, bicycle)

- `_find_collision_overlaps_fcl` prefilters on AABB intersection depth > `overlap_tol`
  (1e-3) on ALL THREE axes, then confirms with `fcl.collide`. So coincident-face
  contact (depth 0 on one axis) is never reported and still counts as "supported"
  for the floating-part QC, while a real penetration needs `allow_overlap`.
- Hollow bores are therefore unnecessary when a *flush* joint is possible: end the
  shaft's cap exactly on the mating face (axle ends at the dropout's inner face,
  pedal spindle starts at the crank arm's outer face) -> contact passes, no overlap.

## Hand-built mesh kit + fit_to_box pre-centring (verified 2026-12, bicycle)

- A ~10-line `_MB` class (prism/tube/ring_x/torus_x/loft over `MeshGeometry.add_vertex`
  + `add_face`) gives total control of every vertex and AABB, is fast, and avoids all
  cq revolve/plane/export surprises. Winding recipes that worked: lateral quad
  `(a[k],a[k2],b[k2],b[k])` for a CCW section in the (u,v) frame with `v = d×u`;
  ring side faces and torus `(i,j),(i+1,j),(i+1,j+1),(i,j+1)` (u then v) both come
  out outward.
- Two different offset conventions in one file is the classic bug: root-part visuals
  must use `origin=Origin(xyz=OFF)` with geometry in DESIGN coords, while child-part
  meshes must be built ALREADY in the part-local frame (no extra `-part_frame` shift).
  Mixing them shifts those parts by the whole frame offset, which then inflates the
  pre-fit union AABB so `fit_to_box` shrinks the entire model (~0.008x here).
- Pre-centring that gives delta≈0 (needed for depth-2 joints) only works if the
  authored extreme points are exactly predictable: tyre bottom = axle_y - R (ring
  angle u=pi exists when nring%4==0), handlebar ends from a cylinder end cap, saddle
  top from a loft's first section. Then `_AUTH_CENTER` can be computed from the same
  constants and `s*C == target` to ~1e-15.
- Front-end clearance that actually bites: with a 0.34 m wheel the tyre's outer
  radius reaches ABOVE the head tube's bottom, so the head tube must sit at
  y >= ~0.70 (crown just above the tyre) and the front axle needs real fork rake
  (~45 mm ahead of the steering axis) or the down tube and fork crown both end up
  inside the tyre's radial band.

## Overlap QC is per-AABB over axes: min over the three axes must be < 5 mm (verified 2026-11, dining chair)

- The compiler `real_overlap` pass reports `depth=(dx,dy,dz)` = per-axis extents of the
  overlap of the two ELEMENT AABBs, and fails when `min(dx,dy,dz) > 0.005`. So a joint
  only needs ONE axis whose overlap extent stays under 5 mm; the other two may be huge.
- Practical consequence for wood joints: a tenon embedded 2 mm into a post still fails if
  the mating bar spans the post's whole cross-section (e.g. a centred side stretcher
  running along z through a leg: overlap extents become 20 x 35 x 28 mm). Fix either by
  keeping the bar's ends exactly at the *physical* (tapered) face so the AABB overlap is
  only the taper sliver, or by an element-scoped `allow_overlap` + `expect_contact` proof.
- `expect_contact`/floating QC does NOT accept a 0.5 mm gap, but a 0.3-1.5 mm embed passes
  both the contact check and the overlap pass (because some axis stays < 5 mm), so tiny
  deliberate embeddings are the cheap way to make parts read as joined.
- Parts authored in world coordinates with articulation `origin=Origin()` (identity) and
  visuals at `origin=Origin()` place correctly and behave under `fit_to_box` (single-level
  star, delta applied once to root visuals and to the identity joint origins).

## Upholstered furniture: rounded slabs + piping seams (verified 2026-01, sofa)

- Reliable soft-cushion primitive: `cq.Sketch().rect(w,d).vertices().fillet(rc)` ->
  `Workplane("XY").placeSketch(sk).extrude(t)`, then collect the two rim edge loops
  via `[e for e in wp.edges().vals() if abs(e.Center().z)<1e-6 or abs(e.Center().z-t)<1e-6]`
  and `wp.newObject(edges).fillet(re)` (ONE call for both loops). Then
  `tessellate_cadquery(shape)` and convert to y-up yourself with
  `vertices = [(x, z, -y) ...]` (det=+1, so winding is preserved). Do not rely on
  `shape.rotate(...)` for lone/lofted solids.
- Welt/piping seam that reads well and stays a single supported visual: an annular
  band from `ExtrudeWithHolesGeometry(rounded_rect_profile(w+2t,d+2t,rc+t),
  [rounded_rect_profile(w,d,rc)], height=0.008, center=True)` whose INNER loop exactly
  coincides with the cushion's flush side band (|y| < t/2 - re). Exact coincidence =>
  contact, zero volume overlap, no QC flags.
- Any decorative cap/rail on a part must be INSET from the faces that other parts
  touch, or it silently becomes the penetrating element (a back-panel cap 5 mm deeper
  than its panel penetrated the back cushion by 6.8 mm).
- With `fit_to_box` on an exact-box model, every decorative add-on must stay inside the
  authored union (cap top exactly at BACK_TOP, not 1.5 mm above) or s drops below 1 and
  the whole sofa shrinks.

## Revolved pottery/vessels via cq polyline revolve (verified 2026-01, plant pot)

- `cq.Workplane("ZX").polyline([(z, r), ...]).close().revolve(360, (0,0), (1,0))`
  is reliable (local u = world Z, v = world X/radius). Trick: close the OUTER
  profile from the rim point back to the axis point `(0, 0)`; the closing edge
  becomes a conical inner surface, so the body is already shell-like and the
  cavity cut only has to shape the inner wall + floor. Subtract a second
  revolved solid whose profile extends ABOVE the rim to get a genuinely open
  mouth, and subtract a `Workplane("XY").workplane(offset=-x).circle(r).extrude(h)`
  cylinder for a drain/bore hole.
- `tessellate_cadquery` emits each cq FACE with its own vertex indices (no
  welding), so a legitimate one-piece solid reports
  `has_raw_disconnected_components: true` while compiled collision count is 1
  and no QC warning fires. Not a defect — don't chase it.
- That per-face vertex duplication is why per-vertex surface noise must be a
  pure function of position: coincident duplicated vertices then displace
  identically and the surface stays crack-free.
- A mesh whose raw components are separate faces gets overlap-report elem names
  like `saucer_body__component_001`; `TestContext` aliases `__component_NNN`
  back to the base visual name, so `allow_overlap(..., elem_b="saucer_body")`
  still matches (element-scoped allowances need BOTH elems named).
- `ctx.expect_origin_distance(...)` compares PART FRAME origins, so after
  `fit_to_box` (which shifts root visuals' origins but leaves the root frame at
  the world origin) a child's part frame sits at the centering delta — the
  "centred under" test must use AABB/element centres, not part origins.
- Scaling the authored mesh so its max radius is exactly the box half-width
  (same factor applied to every visual) keeps `fit_to_box` at s≈1 and keeps the
  seating planes exactly coincident.

## Keeping a swept model inside the --box (verified 2026-12, coffee grinder)

- Budget it up front: `fit_to_box` sizes the REST union, so
  `rest_dim + joint_travel` must stay under the box on every axis. A twist-lock
  (revolute) on a round part is the worst offender: `real_bbox` rotates the part's
  AABB, so a diameter-D ring twisted by θ reports `D(cosθ+sinθ)` — a 0.35 rad twist
  turned a 0.131 m hopper into 0.169 m and blew a 0.15 m box. Keep ω-lock twists
  ≤ ~0.2 rad and/or shrink the round part; a prismatic tray slide must also fit in
  the depth slack (shorten the spout/fork overhang to buy it).
- Box-check loop that works: `compile_model` → `real_bbox` → adjust authored
  overhangs/limits → recompile. The scale is usually set by width or depth, leaving
  1–2 cm of height slack for a lid lift.

## Eyeballing meshes with no numpy/matplotlib (verified 2026-12, Articraft)

- Neither numpy, matplotlib nor PIL exists in the sandbox python. The materialized
  OBJs from the last compile live in `<repo>/.compile_tmp/assets/meshes/`
  (find `-newermt`), and a ~90-line pure-python rasterizer (OBJ `v`/`f` parse →
  orthographic project → painter-sorted barycentric fill → luminance ramp printed as
  ASCII, or PNG via `zlib` + hand-built chunks) is enough to sanity-check silhouette,
  part placement and front/side proportions.

## real_bbox inflates rotating circular parts by √2 (verified 2026-12, Articraft)

- `real_bbox` sweeps the joint range but computes each pose's AABB by rotating the
  part's local AABB (a box) and taking the outer bounds. A round lid that spins about
  its own vertical axis therefore reports width = diameter·√2 (at the 45° sample),
  even though its true footprint is unchanged. With `fit_to_box` sizing the rest union
  to fit the box exactly, any visible revolute spin on a full-diameter round part makes
  `real_bbox` exceed the box limit.
- Fix: use a PRISMATIC lift for lids that must open (real "lift off after unscrewing"),
  which grows the swept box only by the translation amount. Keep the lift small enough
  that rest_height + lift ≤ box height (here 0.132 + 0.015 = 0.147 ≤ 0.15).
- A pile of discrete items (coffee beans, rocks) authored as many ellipsoids merged into
  one MeshGeometry always trips the non-blocking `disconnected_geometry` warning:
  overlapping meshes are NOT welded, so each item is a separate topological island.
  This is the physically correct representation; accept the warning.

## Fitting a swaying/organic plant into a tight box (verified 2026-12, potted plant)

- `fit_to_box` always saturates at least one dimension, so a plant whose leaves sway
  (revolute at the crown) will exceed the box in `real_bbox` unless the SATURATED
  dimension is the one the sway axis leaves invariant. A rotation about the x axis
  preserves all x coordinates: make the plant's WIDTH the limiting dimension (squash
  the foliage front-to-back via `MeshGeometry.scale(sx, 1.0, sz)`), then height and
  depth keep real slack and the swept box still fits.
- Practical recipe: author foliage freely, then post-scale every foliage mesh
  (stem + each leaf, same factors so bases stay welded) by ~(1.0, 1.0, 0.72). Check
  with `real_bbox`: target swept dims comfortably inside the box in every axis.
- Broad ruffled leaves read well as a hand-built thin shell: parametric grid
  (t along the blade, v across), width `W*sin(pi*t**0.8)**0.75` (min-clamped so the
  tip stays closed), cup `-0.34*v^2*w`, edge ripple `0.42*v^6*w*sin(...)`; build top
  and bottom grids offset in y plus rim/tip quads, collapsing the t=0 row to one
  base vertex placed on the stem surface.
- Glaze plaques on a tapered superellipse pot: loft the pot's own cross-section
  offset +1.8 mm, intersect with a box window whose back face sits INSIDE the wall
  thickness — gives a curved proud patch with no corner gaps.

## fit_to_box derives scale from the FULL union AABB (verified 2026-12, digital scale)

- `fit_to_box` scales by `s = min(dims/cur_dims)` of the union of ALL parts at zero pose,
  and a misplaced child part inflates that union enough to shrink the whole model
  (a child 87 mm too far in depth dropped s from 1.07 to 0.79). Symptom: every part is
  uniformly smaller than expected AND off-centre. Invert it to diagnose:
  `pre = (post_aabb - delta)/s` with `delta = post_root_min - s*0_ref`, then compare the
  recovered per-part min/max to the authored numbers — that pinpoints the offending part.
- When authoring a child visual in "world cq coords", remember the part frame: local
  `world_z = -(cq_y_after_build_translate)`. If a helper already centres the shape
  somewhere (e.g. `cy = -PLAT_CZ`), translating into the part frame must SUBTRACT that
  centering, not add it again (double-offset bug).

## Child part visuals live in the CHILD local frame (verified 2026-12)

- Authoring a child part's visuals at "world" coordinates double-offsets them: the part
  frame already sits at the articulation origin, so the geometry lands at 2x the joint
  offset. Symptom: `expect_contact` reports a gap roughly equal to the joint-origin
  height, and the misplaced child also inflates the `fit_to_box` union (too-small scale).
  Fix: build the geometry in world coords then `.translate(0, -joint_origin_y, 0)` before
  `mesh_from_geometry`, keeping the joint `Origin(xyz=(0, y, 0))` as authored.
- `fit_to_box` scales geometry but does NOT scale `MotionLimits.lower/upper`: a prismatic
  upper of 0.055 authored for a 0.21 m object allowed a 55 mm lift on a 0.145 m object.
  Set prismatic limits in POST-scale metres (by hand ≈ `authored * scale`).

## Hand-rolled revolve for hollow glass / vessels (verified 2026-12, Articraft)

- Rather than fight `LatheGeometry.from_shell_profiles` cap semantics, a ~30-line
  `_revolve(points, segments)` that rings a closed (r, h) polygon and stitches quads is
  fully deterministic: outer wall up, top rim inward, inner wall down, bottom back out
  (CW in (r,h)) gives outward normals; collapse `r == 0` points to one shared apex index
  and emit triangles there. Feed the result straight to `mesh_from_geometry`.
- Nested same-part shells (paper filter in a cone, liquid in a glass) must genuinely
  intersect, otherwise the per-part `disconnected_geometry` warning fires. Offset each
  inner shell ~1 mm *proud* of the outer one's wall (a hidden local overlap) and derive
  the inner radii from the outer profile's linear r(y) instead of eyeballing them.
- The per-part island QC warns only (non-blocking); the floating-part QC is blocking and
  needs real face contact at the rest pose.

## CadQuery revolve pitfall (verified 2026-11, Articraft y-up task)

- `cq.Workplane("XZ").polyline(profile).close().revolve(360,(0,0,0),(0,0,1))` does NOT
  reliably produce a solid of revolution in this build: it came back as a huge FLAT disk
  (thin in one axis, radius ~the max profile coordinate). Result: degenerate mesh + wildly
  wrong `fit_to_box` scale. Do NOT use cq `revolve` for lathe/vessel shapes here.
- Reliable path for funnels/bowls/discs/dome+knob lids/hollow cups: SDK
  `LatheGeometry.from_shell_profiles(outer, inner, segments=N)` (hollow shells) and
  `LatheGeometry(profile, segments=N, closed=True)` (solid), profiles are `(radius, z)`
  lists. Bake z-up -> y-up by transforming vertices yourself:
  `geom.vertices = [(x, z, -y) for (x,y,z) in geom.vertices]` (offset added after), then
  `mesh_from_geometry`. This mirrors the cq `rotate(-90 about X)` for boxes.
- Plain cq `Workplane("XY").box(...).edges("|Z").fillet(r).val()` + fuse/cut works fine for
  prismatic housings/panels under `fit_to_box`.
- The compiler "real 3D overlap" QC is effectively per-part AABB overlap: a cup nested in a
  front cavity, or a knob embedded in a panel, trips it (min_depth = per-axis box overlap).
  This is an unavoidable proxy artifact for legitimately nested parts — fix with element-
  scoped `ctx.allow_overlap(body, child, elem_a="housing", elem_b="<child elem>", reason=...)`
  plus an `expect_contact` proof; do not distort geometry to chase it.
- `fit_to_box` fits the REST pose to the given box; `real_bbox` (swept) is legitimately
  larger once joints move (a lid that lifts above a body that already fills full height).

## Workspace / path conventions (verified 2026-11)

- `model.py` in `/mnt/sda/johnli/SEAL/ArtiAgent` can be rewritten by OTHER concurrent
  agent sessions mid-task (different object names appear between my write and my
  compile). Each write_file backs up the previous content to `.trash/<ts>_model.py`,
  so a clobbered revision can be recovered from `.trash` by grep-ing for a unique
  string from my model. Always confirm `model.py` still matches my model (grep a
  unique name) before trusting a compile verdict, and re-write as the last action.

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

## Height-field sheet (cloth) under a thin --box (verified 2026-12, Articraft)

- For a crumpled cloth/rag: author ONE part with one mesh visual and no articulations.
  Build a double skin (top grid `y=h+t/2`, bottom `y=h-t/2`) plus a rim loop of quads
  around the four free edges — that reads as a continuous thin textile with a real
  underside instead of a single-sided plane.
- Normalise the height field by its RANGE, not its max: `s = PEAK/(hi-lo)` and
  `y = (h-lo)*s`. Max-only normalisation lets negative fold creases push total height
  past the box, so `fit_to_box` scales by height and width/depth come out ~0.86x too
  small (a width test failed at 0.230 instead of 0.280).
- Rim winding for outward normals: traverse the boundary CCW as seen from +y (i
  ascending at j=0, then j ascending at i=NU, then i descending, then j descending) and
  emit quads `(top_p, top_q, bottom_q, bottom_p)`.
- Big smooth gaussians alone read as a pillow. Asymmetric cloth character comes from a
  narrow diagonal ridge `exp(-((x-(a+b*z))/w)^2)` with b~0.2, a narrow negative crease
  on another diagonal, offset bunched shoulders, and a rear roll at the back edge.

## Articraft / CadQuery environment quirks (verified 2026-11)

- `fit_to_box(model, center, dims)` does NOT rotate: the model must already be authored
  y-up (+y up, +z front). dims order is (x width, y height, z depth). Only the ROOT
  part's visuals and every joint origin are translated by the centering delta, so put
  all parts directly under the root.
- Authoring pattern that works: build in cq z-up, then `shape.rotate((0,0,0),(1,0,0),-90)`
  to get y-up. In that frame world +x = cq +x, world +y = cq +z, world +z = cq -y.
- Revolve a closed (radius, height) polygon: use `cq.Workplane("ZX")` (normal +Y, no
  left/right mirror warning) with local coords `(u,v) = (height, radius)` and
  `wp.revolve(360, (0,0), (1,0))` (local u axis = world +Z). Workplane("XZ") also works
  but triggers a non-blocking right-handed-convention warning.
- Hollow glass/vessel bodies: outer revolve minus inner revolve (cut tool extends above
  the rim), so the wall thickness is real and the mouth is genuinely open. Fusing a
  curved tube (chain of `cq.Solid.makeSphere` blobs spaced < radius) into the wall and
  then cutting the cavity trims the handle stub flush with the inside surface — clean
  way to get a loop handle that never protrudes into the liquid.
- `mesh_from_cadquery(shape, name, tolerance=..., angular_tolerance=...)`: raising
  tolerance (default 0.001) shrinks exported OBJ size when hundreds of tiny fused
  spheres (ribs, beads) blow the mesh up to >10 MB.

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
- `ctx.expect_gap(positive, negative, axis=...)` measures `positive.min - negative.max`
  (signed ordering along the axis), NOT `positive.max - negative.min`. For "front face is
  recessed behind rim" checks, compare AABBs via `ctx.part_element_world_aabb` instead.
- cq `mesh_from_cadquery` on shapes built on a custom `cq.Plane` / polyline-union chains can
  export triangles displaced from the SDK's recorded AABB (hollow ring cages came back as a
  solid full-size box, scribble offset by >1 m). Prefer hand-built `MeshGeometry` prisms
  (`add_vertex`/`add_face`) in final world coordinates, or plain `Box`/`Cylinder` primitives
  with `Origin.rpy` for tilted parts — those place reliably.
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
- `fit_to_box(model, center, dims)` applies its centering delta to EVERY joint origin,
  so it only shifts a single-level (root -> child) star hierarchy correctly. A
  grandchild joint (base -> cushion -> pillow) gets the delta twice and the part lands
  far away (and inflates the AABB, so the uniform scale comes out too small). Parent
  every part directly to the root.
- `fit_to_box` scales the model, so all `ctx.expect_*` thresholds are in POST-scale
  units. Derive `scale = measured_base_depth / authored_base_depth` in `run_tests()`
  and express gaps/overlaps as multiples of it.
- `export_cadquery_mesh(...).local_aabb` can disagree with the shipped OBJ by ~2 mm.
  For exact seating/mounting, tessellate yourself
  (`verts, faces = tessellate_cadquery(shape)`), build a `MeshGeometry` from it, take
  min/max from those vertices and wrap with `mesh_from_geometry`.
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
- `fit_to_box` translates EVERY articulation origin by its centering delta, so a
  grandchild joint (e.g. pillow on a cushion on the root) gets the delta twice and
  flies metres away. Parent anything whose world placement you compute yourself
  directly to the root part instead of to an intermediate child.
- Authoring convention that works cleanly: build each visual in WORLD coords and
  give the visual `origin = -part_frame`, while the articulation origin is
  `+part_frame` (the two are NOT the same vector). Passing the same negated vector
  to both shifts every child by twice its frame offset.
- `MeshGeometry.rotate_x/rotate_y` records primitive provenance and the exported
  mesh does not match `geom.vertices` afterwards (measured AABB disagreed with the
  hand-computed rotation). For baked tilts, transform the vertex list yourself
  (`geom.vertices = [R @ v for v in geom.vertices]`) and keep the joint origin
  rpy = 0.

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
- CORRECTION (2026-11, re-verified): `fit_to_box(...)` DOES work with
  `mesh_from_cadquery` visuals in the current build. `_scale_geometry` handles
  `Mesh` by multiplying its `scale` tuple, and `geometry_qc._geometry_local_aabb`
  resolves the OBJ via `resolve_mesh_path` for `Mesh` (file must exist + be .obj).
  The earlier "CRASHES on any mesh-backed visual" note applied to
  `MeshGeometry`/`LoftGeometry` descriptors, not to `mesh_from_cadquery` meshes.
  Verified end-to-end with a 5-part CadQuery scale model + `fit_to_box`.
  Still prefer primitives when a mesh adds nothing, but CadQuery housings/pockets
  are fine under `fit_to_box` (just call `fit_to_box` LAST, after all joints are
  authored).
  Rectangular furniture (sofa cushions, backrest, side panels) is fine with
  `Box`; a rolled arm top = `Cylinder` along local `+Z`. `Cylinder` is +Z-aligned,
  so a front-to-back roll already lies correctly with an identity rotation.

## fit_to_box delta is `target - s*center` — pre-centre to protect deep joint trees (verified 2026-12, easel stand)

- `fit_to_box` applies its centring delta to *every* joint origin, including
  grandchild joints where that delta is then double-applied (memory above). Read
  `sdk/_core/v0/fit_to_box.py`: `delta = center - s*cur_center`. So either keep a
  single-level star hierarchy, or author the model already centred on the target
  centre (`OFF = target_center - local_center` added to root visuals AND to
  root-child joint origins only) — then delta ≈ 0 and depth-2/3 chains stay exact.
- Best trick: make the authored AABB height exactly the box height so `s == 1.0`
  (mesh AABB from cq boxes is exact; fillets don't change extents). Then delta is
  ~0 even when the box centre is far from the world origin, and `expect_*`
  thresholds stay in authored units. Verify with a probe: union AABB centre must
  equal the target centre to ~1e-9.
- `real_bbox` inflates *any* rotation by rotating the part AABB, so a jointed
  object whose rest pose exactly saturates the tight axis (here 6 cm height) will
  always report swept dims > box. Check the true swept volume with a small
  pure-python script over the materialized OBJs (rotate vertices exactly) before
  blaming the design — and prefer fold directions that keep geometry above the
  floor.
- A folding easel/stand whose rear leg hangs off the *front frame* drives the
  foot centimetres below the table when the frame folds (verified numerically).
  Parent the rear leg to the root so each mechanism folds independently, and set
  its revolute lower limit to 0 so its own swing never digs below the floor.

## fit_to_box exact pre-centring recipe (verified 2025-11, desk lamp)

- `s = min(box_i / cur_dims_i)`, so `s == 1` needs a dimension to match the box
  *exactly*; a height just under the box gives `s` slightly > 1 and then
  `delta = target - s*cur_center` (~0.3 mm here) still cascades 2x/3x down a joint
  chain and breaks the 1e-6 contact/floating QC. Robust fix: measure the authored
  union AABB once by probe, hardcode `_AUTH_DIMS`/`_AUTH_CENTER`, then
  `_BOX_S = min(box_i/_AUTH_DIMS_i)` and
  `OFF_i = target_i/_BOX_S - _AUTH_CENTER_i`; add OFF to root visuals and to the
  depth-1 joint origins only, keep authored height a hair under the box height so
  the box scale is set by height. fit_to_box then recomputes the identical float
  `s`, new_center == target, delta ~1e-16 and every contact check passes.
- In a y-up model every SDK `Cylinder` visual still points along local +Z, so a
  base disc / foot pad needs `Origin(rpy=(-pi/2,0,0))`; forgetting it leaves a
  disc lying flat on its side and silently inflates the fit_to_box union.
- `expect_overlap` axes must match the real relationship: a shade hanging *above*
  a base overlaps on "xz" (footprint), not "xy". `part_world_position(head)`
  never moves when the joint origin *is* the head frame — use
  `part_element_world_aabb(head, elem=...)` centres for pose checks.

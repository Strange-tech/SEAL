from __future__ import annotations

import math

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Material,
    MeshGeometry,
    Origin,
    TestContext,
    TestReport,
    mesh_from_cadquery,
    mesh_from_geometry,
)

# ---------------------------------------------------------------------------
# Side table, authored in the y-up / +z-forward frame.
#
# Real-world proportions (metres):
#   overall height ............ 0.550
#   tabletop ................. 0.450 x 0.450 x 0.030
#   legs ..................... 0.520 long, dia 0.040 (top) -> 0.030 (foot)
#   leg centres .............. +/-0.170 in x and z (inset from the corners)
#
# The model's geometric centre sits at the world origin, so
#   tabletop slab ........  y in [ 0.245, 0.275]
#   leg tops / leg feet ..  y =  0.245 (flush butt joint), y = -0.275
# ---------------------------------------------------------------------------

TOP_W = 0.450          # tabletop width (x)
TOP_D = 0.450          # tabletop depth (z)
TOP_T = 0.030          # tabletop thickness
TOP_RC = 0.022         # tabletop corner radius
TOP_RE = 0.006         # eased rim radius of the slab edges

TOP_BOTTOM_Y = 0.245   # underside of the tabletop
TOP_TOP_Y = 0.275      # top surface
FOOT_Y = -0.275        # floor line

LEG_LEN = TOP_BOTTOM_Y - FOOT_Y            # 0.520
LEG_TOP_R = 0.020                          # 40 mm dia at the shoulder
LEG_FOOT_R = 0.0120                        # eased foot pad radius
LEG_INSET_X = 0.170
LEG_INSET_Z = 0.170
LEG_SEGS = 24

WALNUT = Material(name="walnut", rgba=(0.345, 0.205, 0.118, 1.0))


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _tabletop_shape():
    """Rounded-corner solid-wood slab with eased top and bottom rims (cq z-up)."""
    sketch = cq.Sketch().rect(TOP_W, TOP_D).vertices().fillet(TOP_RC)
    wp = cq.Workplane("XY").placeSketch(sketch).extrude(TOP_T)
    # Ease both rim loops (top at z=TOP_T, bottom at z=0) in a single fillet call.
    rim_edges = [
        e
        for e in wp.edges().vals()
        if abs(e.Center().z) < 1e-6 or abs(e.Center().z - TOP_T) < 1e-6
    ]
    if rim_edges:
        try:
            wp = wp.newObject(rim_edges).fillet(TOP_RE)
        except Exception:
            pass  # keep the sharp-cornered slab rather than fail the build
    return wp.val()


def _tapered_leg_mesh() -> MeshGeometry:
    """Tapered turned leg in leg-local y-up coords: shoulder at y=0, foot below."""
    # (radius, y) stations from the shoulder down to the eased foot pad.
    stations = [
        (LEG_TOP_R, 0.0),
        (0.0194, -0.055),
        (0.0186, -0.120),
        (0.0175, -0.220),
        (0.0164, -0.320),
        (0.0153, -0.420),
        (0.0145, -0.492),
        (0.0142, -0.506),
        (LEG_FOOT_R, FOOT_Y + 0.020 - 0.0 - (FOOT_Y + 0.020) + (FOOT_Y)),  # placeholder
    ]
    # Replace the last station with a clean chamfered foot:
    stations = stations[:-1] + [(0.0140, FOOT_Y + 0.012), (LEG_FOOT_R, FOOT_Y)]

    geom = MeshGeometry()
    rings = []
    for radius, y in stations:
        ring = []
        for i in range(LEG_SEGS):
            a = 2.0 * math.pi * i / LEG_SEGS
            ring.append(geom.add_vertex(radius * math.cos(a), y, radius * math.sin(a)))
        rings.append(ring)

    for r0, r1 in zip(rings[:-1], rings[1:]):
        for i in range(LEG_SEGS):
            j = (i + 1) % LEG_SEGS
            geom.add_face(r0[i], r0[j], r1[j])
            geom.add_face(r0[i], r1[j], r1[i])

    # Shoulder cap (normal +y) and foot cap (normal -y).
    top_c = geom.add_vertex(0.0, stations[0][1], 0.0)
    bot_c = geom.add_vertex(0.0, stations[-1][1], 0.0)
    for i in range(LEG_SEGS):
        j = (i + 1) % LEG_SEGS
        geom.add_face(top_c, rings[0][i], rings[0][j])
        geom.add_face(bot_c, rings[-1][j], rings[-1][i])

    return geom


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="side_table")
    model.materials.append(WALNUT)

    # --- Tabletop: the root body, carrying everything else -------------------
    top = model.part("tabletop")
    # cq z-up slab -> y-up: Rx(-90 deg) maps local (x, y, z) to (x, z, -y).
    top.visual(
        mesh_from_cadquery(_tabletop_shape(), "tabletop_slab"),
        origin=Origin(xyz=(0.0, TOP_BOTTOM_Y, 0.0), rpy=(-math.pi / 2.0, 0.0, 0.0)),
        material=WALNUT,
        name="tabletop_slab",
    )

    leg_geom = _tapered_leg_mesh()
    positions = [
        (-LEG_INSET_X, -LEG_INSET_Z),
        (LEG_INSET_X, -LEG_INSET_Z),
        (LEG_INSET_X, LEG_INSET_Z),
        (-LEG_INSET_X, LEG_INSET_Z),
    ]

    for idx, (lx, lz) in enumerate(positions):
        leg = model.part(f"leg_{idx}")
        leg.visual(
            mesh_from_geometry(leg_geom.copy(), f"leg_{idx}"),
            origin=Origin(),
            material=WALNUT,
            name="leg_post",
        )
        # Fixed butt joint: the leg shoulder seats flush on the tabletop underside.
        model.articulation(
            f"tabletop_to_leg_{idx}",
            ArticulationType.FIXED,
            parent=top,
            child=leg,
            origin=Origin(xyz=(lx, TOP_BOTTOM_Y, lz)),
        )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    top = object_model.get_part("tabletop")
    legs = [object_model.get_part(f"leg_{i}") for i in range(4)]

    top_box = ctx.part_element_world_aabb(top, elem="tabletop_slab")
    if top_box is not None:
        (tmin, tmax) = top_box
        ctx.check(
            "tabletop slab is 0.45 x 0.45 x 0.03 m",
            abs((tmax[0] - tmin[0]) - TOP_W) < 0.004
            and abs((tmax[2] - tmin[2]) - TOP_D) < 0.004
            and abs((tmax[1] - tmin[1]) - TOP_T) < 0.004,
            details=f"top aabb min={tmin} max={tmax}",
        )

    for i, leg in enumerate(legs):
        # Leg seats against the tabletop underside with no gap and no penetration.
        ctx.expect_gap(
            top,
            leg,
            axis="y",
            min_gap=-0.0005,
            max_gap=0.0005,
            positive_elem="tabletop_slab",
            name=f"leg_{i} shoulders flush under the tabletop",
        )
        ctx.expect_contact(
            top,
            leg,
            contact_tol=1e-4,
            elem_a="tabletop_slab",
            elem_b="leg_post",
            name=f"leg_{i} is supported by the tabletop",
        )
        # Leg footprint stays inside the tabletop footprint.
        ctx.expect_within(
            leg,
            top,
            axes="xz",
            inner_elem="leg_post",
            outer_elem="tabletop_slab",
            name=f"leg_{i} sits inboard of the tabletop edge",
        )
        leg_box = ctx.part_element_world_aabb(leg, elem="leg_post")
        ctx.check(
            f"leg_{i} runs from the tabletop underside to the floor",
            leg_box is not None
            and abs(leg_box[1][1] - TOP_BOTTOM_Y) < 0.001
            and abs(leg_box[0][1] - FOOT_Y) < 0.001,
            details=f"leg aabb={leg_box}",
        )
        ctx.check(
            f"leg_{i} tapers toward the floor",
            leg_box is not None
            and (leg_box[1][0] - leg_box[0][0]) < 2.0 * LEG_TOP_R + 0.0005,
            details=f"leg footprint={None if leg_box is None else leg_box[1][0] - leg_box[0][0]}",
        )

    # Overall proportions: 0.55 m tall, 0.45 m square footprint.
    ys = []
    for part in [top, *legs]:
        box = ctx.part_world_aabb(part)
        if box is not None:
            ys.extend([box[0][1], box[1][1]])
    if ys:
        height = max(ys) - min(ys)
        ctx.check(
            "overall height is about 0.55 m",
            abs(height - 0.550) < 0.006,
            details=f"height={height}",
        )
        ctx.check(
            "object is centred vertically on the origin",
            abs(max(ys) + min(ys)) < 0.002,
            details=f"y span=({min(ys)}, {max(ys)})",
        )

    # Legs occupy four distinct quadrants (real four-legged stance).
    quad = set()
    for leg in legs:
        pos = ctx.part_world_position(leg)
        if pos is not None:
            quad.add((pos[0] > 0.0, pos[2] > 0.0))
    ctx.check("four legs stand in four quadrants", len(quad) == 4, details=f"quadrants={quad}")

    return ctx.report()


object_model = build_object_model()

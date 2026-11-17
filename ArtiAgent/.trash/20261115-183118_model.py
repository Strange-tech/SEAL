from __future__ import annotations

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Origin,
    TestContext,
    TestReport,
    mesh_from_cadquery,
)

# ---------------------------------------------------------------------------
# Coffee table - plain solid walnut slab top on four square posts.
# World frame: y-up, +z = front.  Object centred at the world origin.
# ---------------------------------------------------------------------------

TOP_W = 1.10          # X, long axis
TOP_D = 0.60          # Z, depth (front-back)
TOP_T = 0.045         # slab thickness
HEIGHT = 0.42         # overall table height
LEG = 0.05            # square post section
INSET = 0.05          # post inset from the tabletop edge

LEG_H = HEIGHT - TOP_T
TOP_CY = HEIGHT / 2.0 - TOP_T / 2.0          # slab centre height
LEG_CY = -HEIGHT / 2.0 + LEG_H / 2.0         # post centre height
LEG_X = TOP_W / 2.0 - INSET - LEG / 2.0
LEG_Z = TOP_D / 2.0 - INSET - LEG / 2.0


def _yup(shape):
    """Rotate a CadQuery z-up solid into the y-up world frame."""
    return shape.rotate((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), -90)


def _top_shape():
    wp = cq.Workplane("XY").box(TOP_W, TOP_D, TOP_T)
    # softened plan corners (the four upright edges)
    wp = wp.edges("|Z").fillet(0.008)
    # slightly eased top and bottom rims
    rim = [
        e
        for e in wp.edges().vals()
        if abs(abs(e.Center().z) - TOP_T / 2.0) < 1e-6
    ]
    wp = wp.newObject(rim).fillet(0.006)
    return wp


def _leg_shape():
    wp = cq.Workplane("XY").box(LEG, LEG, LEG_H)
    return wp.edges("|Z").fillet(0.005)


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="coffee_table")

    walnut = model.material("walnut", color=(0.33, 0.20, 0.12))
    walnut_leg = model.material("walnut_leg", color=(0.29, 0.175, 0.105))

    top = model.part("tabletop")
    top.visual(
        mesh_from_cadquery(_yup(_top_shape()), "tabletop_slab"),
        origin=Origin(xyz=(0.0, TOP_CY, 0.0)),
        material=walnut,
        name="top_slab",
    )

    leg_defs = [
        ("leg_0_0", -1.0, -1.0),
        ("leg_0_1", -1.0, 1.0),
        ("leg_1_0", 1.0, -1.0),
        ("leg_1_1", 1.0, 1.0),
    ]

    for name, sx, sz in leg_defs:
        x = sx * LEG_X
        z = sz * LEG_Z
        leg = model.part(name)
        # The post geometry is authored in its own part frame, which the
        # articulation places at (x, LEG_CY, z) under the tabletop.
        leg.visual(
            mesh_from_cadquery(_yup(_leg_shape()), f"{name}_post"),
            origin=Origin(),
            material=walnut_leg,
            name="post",
        )
        model.articulation(
            f"tabletop_to_{name}",
            ArticulationType.FIXED,
            parent=top,
            child=leg,
            origin=Origin(xyz=(x, LEG_CY, z)),
        )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    top = object_model.get_part("tabletop")

    leg_names = ["leg_0_0", "leg_0_1", "leg_1_0", "leg_1_1"]

    # Every post is physically seated against the underside of the slab.
    for name in leg_names:
        leg = object_model.get_part(name)
        ctx.expect_contact(
            leg,
            top,
            elem_a="post",
            elem_b="top_slab",
            name=f"{name} seated on tabletop",
        )
        ctx.expect_overlap(
            leg,
            top,
            axes="xz",
            elem_a="post",
            elem_b="top_slab",
            min_overlap=LEG - 0.002,
            name=f"{name} under tabletop footprint",
        )

    # Overall silhouette: 1.10 wide x 0.42 tall x 0.60 deep.
    ctx.check(
        "table overall width",
        abs(ctx.part_world_aabb(top)[1][0] - ctx.part_world_aabb(top)[0][0] - TOP_W) < 0.01,
        details="tabletop width should be 1.10 m",
    )
    ctx.check(
        "table overall depth",
        abs(ctx.part_world_aabb(top)[1][2] - ctx.part_world_aabb(top)[0][2] - TOP_D) < 0.01,
        details="tabletop depth should be 0.60 m",
    )

    # Posts stand on the floor well below the slab and are inset from its rim.
    for name in leg_names:
        leg = object_model.get_part(name)
        lo, hi = ctx.part_world_aabb(leg)
        ctx.check(
            f"{name} reaches the floor",
            abs(lo[1] - (-HEIGHT / 2.0)) < 0.002,
            details=f"leg bottom at {lo[1]:.4f}",
        )
        ctx.expect_within(
            leg,
            top,
            axes="xz",
            margin=0.0,
            inner_elem="post",
            outer_elem="top_slab",
            name=f"{name} inset inside tabletop footprint",
        )

    return ctx.report()


object_model = build_object_model()

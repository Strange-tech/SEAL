from __future__ import annotations

import math

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Inertial,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    mesh_from_geometry,
    tessellate_cadquery,
)
from sdk import MeshGeometry

# ---------------------------------------------------------------------------
# Coffee table, y-up / +z-forward authoring frame.
#
#   x = width  (short side, 0.60 m)
#   y = height (0.42 m)
#   z = depth  (long side, 1.10 m)
#
# Actually we lay the long side on X so the silhouette matches the layout box
# (wide + low coffee table seen from the front).
# ---------------------------------------------------------------------------

TOP_LEN = 1.10      # long dimension (x)
TOP_DEPTH = 0.60    # short dimension (z)
TOP_THICK = 0.035
TOP_CORNER_R = 0.045
TOP_EDGE_R = 0.008

HEIGHT = 0.42
LEG_H = HEIGHT - TOP_THICK          # 0.385
LEG_TOP = 0.050                     # square section at the top
LEG_BOT = 0.035                     # tapered section near the floor
LEG_INSET = 0.050                   # inset from tabletop edge

# leg centres in the tabletop frame
LEG_X = TOP_LEN / 2.0 - LEG_INSET - LEG_TOP / 2.0
LEG_Z = TOP_DEPTH / 2.0 - LEG_INSET - LEG_TOP / 2.0

TOP_BOTTOM_Y = HEIGHT / 2.0 - TOP_THICK      # 0.175
TOP_CENTER_Y = HEIGHT / 2.0 - TOP_THICK / 2.0

WOOD_BASE = (0.44, 0.28, 0.16, 1.0)
WOOD_LEG = (0.38, 0.24, 0.14, 1.0)


def _to_mesh(shape, name: str) -> object:
    """Tessellate a CadQuery shape and convert z-up -> y-up (x, z, -y)."""
    verts, tris = tessellate_cadquery(shape, tolerance=0.0006, angular_tolerance=0.12)
    geom = MeshGeometry()
    for (x, y, z) in verts:
        geom.add_vertex(x, z, -y)
    for (a, b, c) in tris:
        geom.add_face(a, b, c)
    return mesh_from_geometry(geom, name)


def _build_top_shape():
    """Rounded-rect slab with softened top/bottom rims."""
    sk = cq.Sketch().rect(TOP_LEN, TOP_DEPTH).vertices().fillet(TOP_CORNER_R)
    slab = cq.Workplane("XY").placeSketch(sk).extrude(TOP_THICK)
    rim_edges = [
        e
        for e in slab.edges().vals()
        if abs(e.Center().z) < 1e-7 or abs(e.Center().z - TOP_THICK) < 1e-7
    ]
    slab = slab.newObject(rim_edges).fillet(TOP_EDGE_R)
    # centre the slab about z=0 so the y-up conversion lands it symmetric
    return slab.translate((0.0, 0.0, -TOP_THICK / 2.0))


def _build_leg_shape():
    """Tapered square post: top face at cq z=0, foot at cq z=-LEG_H."""
    leg = (
        cq.Workplane("XY")
        .rect(LEG_TOP, LEG_TOP)
        .workplane(offset=-LEG_H)
        .rect(LEG_BOT, LEG_BOT)
        .loft()
    )
    return leg


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="coffee_table")

    model.material("wood_walnut", rgba=WOOD_BASE, texture="wood")
    model.material("wood_walnut_leg", rgba=WOOD_LEG, texture="wood")

    top = model.part("tabletop")
    top_mesh = _to_mesh(_build_top_shape(), "tabletop_slab")
    top.visual(
        top_mesh,
        origin=Origin(xyz=(0.0, TOP_CENTER_Y, 0.0)),
        material="wood_walnut",
        name="tabletop_slab",
    )
    leg_shape = _build_leg_shape()
    for i, (sx, sz) in enumerate(
        [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    ):
        leg = model.part(f"leg_{i}")
        leg.visual(
            _to_mesh(leg_shape, f"leg_{i}_post"),
            origin=Origin(),
            material="wood_walnut_leg",
            name="leg_post",
        )
        model.articulation(
            f"tabletop_to_leg_{i}",
            ArticulationType.FIXED,
            parent=top,
            child=leg,
            origin=Origin(xyz=(sx * LEG_X, TOP_BOTTOM_Y, sz * LEG_Z)),
        )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    top = object_model.get_part("tabletop")
    legs = [object_model.get_part(f"leg_{i}") for i in range(4)]

    # every leg is rigidly joined to the underside of the tabletop
    for i, leg in enumerate(legs):
        ctx.expect_contact(
            leg,
            top,
            contact_tol=1e-4,
            elem_a="leg_post",
            elem_b="tabletop_slab",
            name=f"leg_{i} seated on tabletop underside",
        )
        ctx.expect_within(
            leg,
            top,
            axes="xz",
            inner_elem="leg_post",
            outer_elem="tabletop_slab",
            margin=0.0,
            name=f"leg_{i} inset inside tabletop footprint",
        )

    # the four legs sit inset from the tabletop edges on both in-plane axes
    ctx.expect_overlap(
        legs[0], legs[1], axes="z", min_overlap=0.02, name="legs share depth band"
    )

    # feet are coplanar on the floor
    floor_ref = None
    for i, leg in enumerate(legs):
        aabb = ctx.part_element_world_aabb(leg, elem="leg_post")
        if aabb is None:
            ctx.fail(f"leg_{i} geometry available", "missing leg geometry")
            continue
        center_x = (aabb[0][0] + aabb[1][0]) / 2.0
        center_z = (aabb[0][2] + aabb[1][2]) / 2.0
        ctx.check(
            f"leg_{i} stays inside tabletop footprint",
            abs(center_x) + LEG_BOT / 2.0 <= TOP_LEN / 2.0
            and abs(center_z) + LEG_BOT / 2.0 <= TOP_DEPTH / 2.0,
            details=f"leg {i} at ({center_x:.3f}, {center_z:.3f})",
        )
        if floor_ref is None:
            floor_ref = aabb[0][1]
        else:
            ctx.check(
                f"leg_{i} foot coplanar with first foot",
                abs(aabb[0][1] - floor_ref) < 1e-4,
                details=f"{aabb[0][1]:.5f} vs {floor_ref:.5f}",
            )

    # overall proportions: broad, low coffee table
    top_aabb = ctx.part_element_world_aabb(top, elem="tabletop_slab")
    if top_aabb is not None:
        width = top_aabb[1][0] - top_aabb[0][0]
        depth = top_aabb[1][2] - top_aabb[0][2]
        thickness = top_aabb[1][1] - top_aabb[0][1]
        total_h = top_aabb[1][1] - (floor_ref if floor_ref is not None else 0.0)
        ctx.check("tabletop width", abs(width - TOP_LEN) < 0.005, details=f"{width:.4f}")
        ctx.check("tabletop depth", abs(depth - TOP_DEPTH) < 0.005, details=f"{depth:.4f}")
        ctx.check(
            "tabletop thickness",
            abs(thickness - TOP_THICK) < 0.005,
            details=f"{thickness:.4f}",
        )
        ctx.check(
            "overall height",
            abs(total_h - HEIGHT) < 0.006,
            details=f"{total_h:.4f}",
        )

    return ctx.report()


object_model = build_object_model()

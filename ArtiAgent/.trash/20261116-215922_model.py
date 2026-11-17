from __future__ import annotations

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Material,
    Origin,
    TestContext,
    TestReport,
    mesh_from_cadquery,
)

# ---------------------------------------------------------------------------
# Real-world dimensions (metres) for a dining table, 4-seat footprint.
# Long side laid on X to match the layout box.
# ---------------------------------------------------------------------------
TABLE_LEN = 1.4      # x, length
TABLE_WID = 0.9      # z, width
TOP_TH = 0.040       # y, tabletop thickness
TOTAL_H = 0.750      # overall height

LEG = 0.070          # square leg section
INSET = 0.050        # leg outer face inset from tabletop edge

# Derived vertical layout (geometric centre at origin, y-up, +z forward).
TOP_CY = TOTAL_H / 2.0 - TOP_TH / 2.0          # tabletop slab centre
TOP_BOTTOM = TOTAL_H / 2.0 - TOP_TH            # underside of top
FLOOR = -TOTAL_H / 2.0                          # ground plane
LEG_H = TOP_BOTTOM - FLOOR
LEG_CY = (TOP_BOTTOM + FLOOR) / 2.0

# Leg centre coordinates.
LEG_X = TABLE_LEN / 2.0 - INSET - LEG / 2.0
LEG_Z = TABLE_WID / 2.0 - INSET - LEG / 2.0

# Natural matte hardwood finish.
WOOD_TOP = Material(name="oak_top", rgba=(0.66, 0.47, 0.29, 1.0))
WOOD_LEG = Material(name="oak_leg", rgba=(0.58, 0.40, 0.24, 1.0))


def _rounded_box(lx: float, ly: float, lz: float, r: float, name: str):
    """A y-up rounded rectangular block, centred at the local origin.

    lx = world x, ly = world y (vertical), lz = world z.
    """
    # Build z-up (cq x=lx, cq y=lz, cq z=ly), fillet all edges, then tip to y-up.
    wp = cq.Workplane("XY").box(lx, lz, ly)
    try:
        wp = wp.edges().fillet(r)
    except Exception:
        pass
    solid = wp.val().rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), -90)
    return mesh_from_cadquery(solid, name)


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="dining_table")

    # Root: the tabletop. Its frame sits at the geometric centre of the object.
    top = model.part("tabletop")
    top.visual(
        _rounded_box(TABLE_LEN, TOP_TH, TABLE_WID, 0.008, "tabletop_slab"),
        origin=Origin(xyz=(0.0, TOP_CY, 0.0)),
        material=WOOD_TOP,
        name="tabletop_slab",
    )

    # Four square legs, one near each corner, each fixed under the top.
    corners = [
        (LEG_X, LEG_Z),
        (LEG_X, -LEG_Z),
        (-LEG_X, LEG_Z),
        (-LEG_X, -LEG_Z),
    ]
    for i, (cx, cz) in enumerate(corners):
        leg = model.part(f"leg_{i}")
        leg.visual(
            _rounded_box(LEG, LEG_H, LEG, 0.006, f"leg_post_{i}"),
            origin=Origin(xyz=(0.0, 0.0, 0.0)),
            material=WOOD_LEG,
            name=f"leg_post_{i}",
        )
        model.articulation(
            f"tabletop_to_leg_{i}",
            ArticulationType.FIXED,
            parent=top,
            child=leg,
            origin=Origin(xyz=(cx, LEG_CY, cz)),
        )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    top = object_model.get_part("tabletop")
    legs = [object_model.get_part(f"leg_{i}") for i in range(4)]

    # Each leg must physically sit against the underside of the tabletop.
    for i, leg in enumerate(legs):
        ctx.expect_contact(
            leg, top,
            elem_a=f"leg_post_{i}",
            elem_b="tabletop_slab",
            contact_tol=1e-4,
            name=f"leg_{i} meets tabletop underside",
        )
        # Legs stay within the tabletop footprint in plan view.
        ctx.expect_within(
            leg, top,
            axes="xz",
            elem_a=f"leg_post_{i}",
            elem_b="tabletop_slab",
            margin=1e-6,
            name=f"leg_{i} within tabletop footprint",
        )

    # Four legs reach the floor and share a common, level base.
    leg_aabbs = [ctx.part_element_world_aabb(leg, elem=f"leg_post_{i}") for i, leg in enumerate(legs)]
    floor_vals = [aabb[0][1] for aabb in leg_aabbs if aabb is not None]
    ctx.check(
        "legs rest on the floor",
        len(floor_vals) == 4 and all(abs(v - FLOOR) < 1e-3 for v in floor_vals),
        details=f"leg bottoms vs floor {FLOOR}: {floor_vals}",
    )

    # Overall height matches the intended 0.75 m.
    top_aabb = ctx.part_element_world_aabb(top, elem="tabletop_slab")
    if top_aabb is not None:
        height = top_aabb[1][1] - FLOOR
        ctx.check(
            "table overall height ~0.75 m",
            abs(height - TOTAL_H) < 1e-3,
            details=f"height={height}",
        )

    return ctx.report()


object_model = build_object_model()

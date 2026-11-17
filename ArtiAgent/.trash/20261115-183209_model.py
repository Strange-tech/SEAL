from __future__ import annotations

from sdk import (
    ArticulatedObject,
    ArticulationType,
    ExtrudeGeometry,
    LoftGeometry,
    Origin,
    TestContext,
    TestReport,
    mesh_from_geometry,
    rounded_rect_profile,
)

# ---------------------------------------------------------------------------
# Simple four-legged wooden side chair (light oak, all rigid joints).
#
# World frame: y-up, +z = front, +x = width.  Chosen so the assembly's
# geometric centre sits near the world origin.
# ---------------------------------------------------------------------------

# Design (pre-centring) dimensions, in metres.
SEAT_W = 0.45
SEAT_D = 0.45
SEAT_T = 0.035
LEG_TOP = 0.040        # square section at the seat
LEG_BOT = 0.030        # square section at the floor
SEAT_TOP_Y = 0.0       # seat top surface (design frame)
LEG_INSET = 0.040      # leg centre inset from the seat edge
LEG_LEN = 0.415
BACK_W = 0.45
BACK_H = 0.42
BACK_T = 0.020
BACK_RECLINE = -0.10   # radians, top leans rearward (-z)

LEG_HALF_X = SEAT_W / 2.0 - LEG_INSET   # 0.185
LEG_HALF_Z = SEAT_D / 2.0 - LEG_INSET

# Small whole-assembly offset so the geometric centre lands at the origin.
OFFY = 0.016
OFFZ = 0.0135


def _yup(geom, dy=0.0, dz=0.0):
    """Convert z-up authored geometry to the y-up world frame, then shift."""
    geom.vertices = [(x, z + dy, -y + dz) for (x, y, z) in geom.vertices]
    return geom


def _square(size, z):
    h = size / 2.0
    return [(-h, -h, z), (h, -h, z), (h, h, z), (-h, h, z)]


def _leg_mesh(top_size, bot_size, length):
    """Tapered square leg, part frame at its top face, extending down in -y."""
    geom = LoftGeometry(
        [_square(top_size, 0.0), _square(bot_size, -length)],
        cap=True,
        closed=True,
    )
    return _yup(geom)


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="wooden_side_chair")

    oak = model.material("light_oak", rgba=(0.80, 0.64, 0.44, 1.0))

    # --- Seat (root part) ------------------------------------------------
    seat = model.part("seat")
    seat_prof = rounded_rect_profile(SEAT_W, SEAT_D, 0.030, corner_segments=8)
    seat_slab = ExtrudeGeometry(seat_prof, SEAT_T, cap=True, center=True)
    _yup(seat_slab, dy=-SEAT_T / 2.0 + OFFY, dz=OFFZ)
    seat.visual(
        mesh_from_geometry(seat_slab, "seat_slab"),
        material=oak,
        name="seat_slab",
    )

    # --- Four legs -------------------------------------------------------
    leg_specs = [
        ("front_left_leg", LEG_HALF_X, LEG_HALF_Z),
        ("front_right_leg", -LEG_HALF_X, LEG_HALF_Z),
        ("rear_left_leg", LEG_HALF_X, -LEG_HALF_Z),
        ("rear_right_leg", -LEG_HALF_X, -LEG_HALF_Z),
    ]
    for name, lx, lz in leg_specs:
        leg = model.part(name)
        leg.visual(
            mesh_from_geometry(_leg_mesh(LEG_TOP, LEG_BOT, LEG_LEN), name),
            material=oak,
            name=name,
        )
        model.articulation(
            f"seat_to_{name}",
            ArticulationType.FIXED,
            parent=seat,
            child=leg,
            origin=Origin(xyz=(lx, -SEAT_T + OFFY, lz + OFFZ)),
        )

    # --- Backrest --------------------------------------------------------
    back = model.part("backrest")
    back_prof = rounded_rect_profile(BACK_W, BACK_H, 0.030, corner_segments=8)
    back_panel = ExtrudeGeometry(back_prof, BACK_T, cap=True, center=True)
    back_panel.translate(0.0, BACK_H / 2.0, 0.0)  # bottom face at local y=0
    back.visual(
        mesh_from_geometry(back_panel, "backrest_panel"),
        material=oak,
        name="backrest_panel",
    )
    model.articulation(
        "seat_to_backrest",
        ArticulationType.FIXED,
        parent=seat,
        child=back,
        origin=Origin(
            xyz=(0.0, SEAT_TOP_Y + OFFY, -SEAT_D / 2.0 + 0.025 + OFFZ),
            rpy=(BACK_RECLINE, 0.0, 0.0),
        ),
    )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    seat = object_model.get_part("seat")
    back = object_model.get_part("backrest")
    legs = [
        object_model.get_part(n)
        for n in (
            "front_left_leg",
            "front_right_leg",
            "rear_left_leg",
            "rear_right_leg",
        )
    ]

    # Legs seat flush against the underside of the seat slab.
    for leg in legs:
        ctx.expect_contact(leg, seat, contact_tol=2e-3,
                           name=f"{leg.name} touches seat underside")

    # Backrest bottom rests on the seat top.
    ctx.expect_contact(back, seat, contact_tol=2e-3,
                       name="backrest contacts seat top")

    # All four legs reach down to the floor (-0.45 + small offset).
    floor_y = -LEG_LEN - SEAT_T + OFFY
    for leg in legs:
        lo = ctx.part_world_aabb(leg)[0]
        ctx.check(
            f"{leg.name} reaches floor",
            abs(lo[1] - floor_y) < 1e-3,
            details=f"leg min y={lo[1]:.4f}, expected={floor_y:.4f}",
        )

    # Backrest sits toward the rear half of the chair.
    back_box = ctx.part_element_world_aabb(back, elem="backrest_panel")
    if back_box is not None:
        ctx.check(
            "backrest sits toward the rear",
            back_box[1][2] < 0.10,
            details=f"backrest rear-extent max z={back_box[1][2]:.4f}",
        )

    # Overall proportions: believable chair size.
    dims = ctx.part_world_aabb(seat)
    if dims is not None:
        sx = dims[1][0] - dims[0][0]
        ctx.check("seat width ~0.45 m", abs(sx - 0.45) < 0.02,
                  details=f"seat width={sx:.3f}")

    # Whole-model height in a believable range (0.80-0.95 m).
    all_parts = [seat, back, *legs]
    ymin = min(ctx.part_world_aabb(p)[0][1] for p in all_parts)
    ymax = max(ctx.part_world_aabb(p)[1][1] for p in all_parts)
    ctx.check("overall height ~0.85-0.95 m", 0.80 < (ymax - ymin) < 0.95,
              details=f"height={ymax - ymin:.3f}")

    return ctx.report()


object_model = build_object_model()

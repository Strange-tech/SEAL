from __future__ import annotations

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Material,
    MeshGeometry,
    Origin,
    TestContext,
    TestReport,
    mesh_from_geometry,
    tessellate_cadquery,
)

# ---------------------------------------------------------------------------
# Three-seat sofa, modelled as a static assembly of FIXED joints.
#
# Convention: world is y-up, +z is front, +x is width.  The whole object is
# authored so its geometric centre sits at the world origin (0,0,0).
#
# Design coordinates use floor = y 0 (easy to reason about); SHIFT_Y re-centres
# the finished object on the origin.
# ---------------------------------------------------------------------------

SHIFT_Y = -0.425  # floor(0)..back-top(0.85) -> -0.425..+0.425


# ---------------------------------------------------------------------------
# mesh helpers
# ---------------------------------------------------------------------------
def _yup(verts, faces, name):
    """Convert a CadQuery (z-up) tessellation into a y-up sdk Mesh."""
    v = [(x, z, -y) for (x, y, z) in verts]
    return mesh_from_geometry(MeshGeometry(vertices=list(v), faces=list(faces)), name)


def rounded_block(w, h, d, r, name, tol=0.0008):
    """A box (w x h x d) with all 12 edges rounded -> upholstered read.

    Built in cq (z-up) as box(w, d, h); after the y-up swap the world extents
    are exactly (w, h, d), centred on the origin.
    """
    shape = cq.Workplane("XY").box(w, d, h).edges().fillet(r)
    verts, faces = tessellate_cadquery(shape.val(), tolerance=tol)
    return _yup(verts, faces, name)


def tapered_leg(r_bottom, r_top, h, name, tol=0.0006):
    """Truncated cone leg, base at y=0, top at y=h (widest at the top)."""
    solid = cq.Solid.makeCone(r_bottom, r_top, h)
    verts, faces = tessellate_cadquery(solid, tolerance=tol)
    return _yup(verts, faces, name)


# ---------------------------------------------------------------------------
# dimensions (design coords, floor = 0)
# ---------------------------------------------------------------------------
W_HALF = 1.18          # total width 2.36
Z_BACK, Z_FRONT = -0.46, 0.46   # depth 0.92

BASE_Y0, BASE_Y1 = 0.10, 0.30   # upholstered base
SEAT_TOP = 0.45                 # seat cushion top
ARM_TOP = 0.65
BACK_TOP = 0.85

ARM_W = 0.19
ARM_XC = 1.18 - ARM_W / 2       # +/-1.085

BACK_T = 0.14                   # back frame thickness
BACK_Z0 = Z_BACK                # -0.46
BACK_Z1 = Z_BACK + BACK_T       # -0.32

CUSH_W = 0.64
CUSH_XC = (-0.66, 0.0, 0.66)

SEAT_D = 0.62
SEAT_ZC = (BACK_Z1 + (BACK_Z1 + SEAT_D)) / 2  # centre front-of-back-frame
SEAT_Y0, SEAT_Y1 = BASE_Y1, SEAT_TOP

BACKCUSH_T = 0.18
BACKCUSH_Y0, BACKCUSH_Y1 = SEAT_TOP, 0.78
BACKCUSH_ZC = BACK_Z1 + BACKCUSH_T / 2

LEG_H = 0.10


def _block(part, w, h, d, r, xc, yc, zc, mat, name):
    part.visual(
        rounded_block(w, h, d, r, name),
        origin=Origin(xyz=(xc, yc + SHIFT_Y, zc)),
        material=mat,
        name=name,
    )


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="three_seat_sofa")

    fabric = model.material(name="fabric", rgba=(0.71, 0.69, 0.63, 1.0))
    walnut = model.material(name="walnut", rgba=(0.21, 0.12, 0.07, 1.0))

    # --- root: upholstered base frame -------------------------------------
    frame = model.part("frame")
    _block(
        frame, 2.36, BASE_Y1 - BASE_Y0, 0.92, 0.03,
        0.0, (BASE_Y0 + BASE_Y1) / 2, 0.0,
        fabric, "base_frame",
    )

    parts = {"frame": frame}

    # --- back frame -------------------------------------------------------
    back_frame = model.part("back_frame")
    _block(
        back_frame, 1.98, BACK_TOP - BASE_Y1, BACK_T, 0.04,
        0.0, (BASE_Y1 + BACK_TOP) / 2, (BACK_Z0 + BACK_Z1) / 2,
        fabric, "back_frame",
    )
    parts["back_frame"] = back_frame

    # --- arms -------------------------------------------------------------
    for i, xc in enumerate((-ARM_XC, ARM_XC)):
        arm = model.part(f"arm_{i}")
        _block(
            arm, ARM_W, ARM_TOP - BASE_Y1, 0.92, 0.05,
            xc, (BASE_Y1 + ARM_TOP) / 2, 0.0,
            fabric, f"arm_{i}",
        )
        parts[f"arm_{i}"] = arm

    # --- legs -------------------------------------------------------------
    leg_geo_cache = None
    leg_xs = (-1.02, 1.02)
    leg_zs = (-0.40, 0.40)
    n = 0
    for lx in leg_xs:
        for lz in leg_zs:
            leg = model.part(f"leg_{n}")
            leg.visual(
                tapered_leg(0.018, 0.030, LEG_H, f"leg_{n}"),
                origin=Origin(xyz=(lx, SHIFT_Y, lz)),
                material=walnut,
                name=f"leg_{n}",
            )
            parts[f"leg_{n}"] = leg
            n += 1

    # --- seat cushions ----------------------------------------------------
    for i, xc in enumerate(CUSH_XC):
        c = model.part(f"seat_cushion_{i}")
        _block(
            c, CUSH_W, SEAT_Y1 - SEAT_Y0, SEAT_D, 0.045,
            xc, (SEAT_Y0 + SEAT_Y1) / 2, SEAT_ZC,
            fabric, f"seat_cushion_{i}",
        )
        parts[f"seat_cushion_{i}"] = c

    # --- back cushions ----------------------------------------------------
    for i, xc in enumerate(CUSH_XC):
        c = model.part(f"back_cushion_{i}")
        _block(
            c, CUSH_W, BACKCUSH_Y1 - BACKCUSH_Y0, BACKCUSH_T, 0.05,
            xc, (BACKCUSH_Y0 + BACKCUSH_Y1) / 2, BACKCUSH_ZC,
            fabric, f"back_cushion_{i}",
        )
        parts[f"back_cushion_{i}"] = c

    # --- fixed joints (authored in world coords, identity child frames) ---
    for name, part in parts.items():
        if name == "frame":
            continue
        model.articulation(
            f"frame_to_{name}",
            ArticulationType.FIXED,
            parent=frame,
            child=part,
            origin=Origin(),
        )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    try:
        model = object_model
    except NameError:
        model = build_object_model()

    frame = model.get_part("frame")

    # three seat modules + three back cushions
    for i in range(3):
        ctx.check(f"seat_cushion_{i} present", model.get_part(f"seat_cushion_{i}") is not None)
        ctx.check(f"back_cushion_{i} present", model.get_part(f"back_cushion_{i}") is not None)

    # every functional part is a direct fixed child of the root
    for name in (
        "back_frame", "arm_0", "arm_1", "leg_0", "leg_1", "leg_2", "leg_3",
        "seat_cushion_0", "seat_cushion_1", "seat_cushion_2",
        "back_cushion_0", "back_cushion_1", "back_cushion_2",
    ):
        joint = model.get_articulation(f"frame_to_{name}")
        ctx.check(f"{name} fixed to root", joint.articulation_type == ArticulationType.FIXED)

    # cushions seat onto the base and lean on the back frame
    for i in range(3):
        ctx.expect_contact(model.get_part(f"seat_cushion_{i}"), frame)
        ctx.expect_contact(model.get_part(f"back_cushion_{i}"), model.get_part("back_frame"))

    # arms stand on the base frame
    ctx.expect_contact(model.get_part("arm_0"), frame)
    ctx.expect_contact(model.get_part("arm_1"), frame)
    # legs meet the underside of the base
    for n in range(4):
        ctx.expect_contact(model.get_part(f"leg_{n}"), frame)

    # seat cushions rest just above the base top, back cushions above seats
    ctx.expect_gap(
        model.get_part("seat_cushion_1"), frame, axis="y",
        max_gap=0.002, max_penetration=0.002,
    )

    return ctx.report()


object_model = build_object_model()

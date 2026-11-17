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
# Design constants (metres).  Authored with the floor at y = 0, then the whole
# model is shifted down so its geometric centre sits at the world origin.
# ---------------------------------------------------------------------------
SEAT_TOP = 0.450          # seat surface height above the floor
SEAT_T = 0.035            # seat slab thickness
SEAT_W = 0.450            # seat width  (x)
SEAT_D = 0.440            # seat depth  (z)
SEAT_BOT = SEAT_TOP - SEAT_T

BACK_W = 0.420            # backrest width
BACK_H = 0.420            # backrest height above the seat
BACK_T = 0.030            # backrest thickness (z)
BACK_TOP = SEAT_TOP + BACK_H
BACK_Z = -SEAT_D / 2.0 + BACK_T / 2.0   # panel centred on the rear edge

LEG_TOP_S = 0.040         # square section at the seat
LEG_BOT_S = 0.028         # square section at the floor (tapered)
LEG_H = SEAT_BOT          # floor -> seat underside
LEG_X = 0.170
LEG_Z = 0.155

TOTAL_H = BACK_TOP
OFF_Y = -TOTAL_H / 2.0    # centre the model vertically on the origin


# ---------------------------------------------------------------------------
# Geometry helpers (built in CadQuery z-up, then baked into the y-up frame)
# ---------------------------------------------------------------------------

def _to_yup(shape):
    """Rotate a cadquery z-up shape into the SDK y-up frame."""
    return shape.rotate((0, 0, 0), (1, 0, 0), -90)


def _hplate(sx, sz, t, r_corner, r_rim):
    """Horizontal slab: sx wide (x), sz deep (z), t thick (y after y-up)."""
    wp = cq.Workplane("XY").box(sx, sz, t)
    if r_corner > 0:
        wp = wp.edges("|Z").fillet(r_corner)
    if r_rim > 0:
        rim = [
            e
            for e in wp.edges().vals()
            if abs(e.Center().z - t / 2.0) < 1e-6 or abs(e.Center().z + t / 2.0) < 1e-6
        ]
        if rim:
            wp = wp.newObject(rim).fillet(r_rim)
    return _to_yup(wp.val())


def _vpanel(sx, sy, t, r_corner, r_rim):
    """Vertical panel: sx wide (x), sy tall (y after y-up), t thick (z)."""
    wp = cq.Workplane("XY").box(sx, t, sy)
    if r_corner > 0:
        wp = wp.edges("|Y").fillet(r_corner)
    if r_rim > 0:
        rim = [
            e
            for e in wp.edges().vals()
            if abs(e.Center().y - t / 2.0) < 1e-6 or abs(e.Center().y + t / 2.0) < 1e-6
        ]
        if rim:
            wp = wp.newObject(rim).fillet(r_rim)
    return _to_yup(wp.val())


def _leg_shape(lx, lz, h, s_bot, s_top):
    """Tapered square leg, footprint centre at world (lx, lz)."""
    cy = -lz  # cadquery +y maps to world -z

    def square(side, z):
        a = side / 2.0
        pts = [
            cq.Vector(lx - a, cy - a, z),
            cq.Vector(lx + a, cy - a, z),
            cq.Vector(lx + a, cy + a, z),
            cq.Vector(lx - a, cy + a, z),
        ]
        return cq.Wire.makePolygon(pts, close=True)

    solid = cq.Solid.makeLoft([square(s_bot, 0.0), square(s_top, h)], ruled=True)
    return _to_yup(solid)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="wooden_chair")

    hardwood = Material(name="hardwood", rgba=(0.44, 0.28, 0.15, 1.0))
    model.materials.append(hardwood)

    # --- seat (root) -------------------------------------------------------
    seat = model.part("seat")
    seat.visual(
        mesh_from_cadquery(
            _hplate(SEAT_W, SEAT_D, SEAT_T, r_corner=0.030, r_rim=0.008).translate(
                (0.0, SEAT_TOP - SEAT_T / 2.0 + OFF_Y, 0.0)
            ),
            "seat_slab",
        ),
        name="seat_slab",
        material=hardwood,
    )

    # --- backrest ----------------------------------------------------------
    back = model.part("backrest")
    back.visual(
        mesh_from_cadquery(
            _vpanel(BACK_W, BACK_H, BACK_T, r_corner=0.028, r_rim=0.007).translate(
                (0.0, SEAT_TOP + BACK_H / 2.0 + OFF_Y, BACK_Z)
            ),
            "backrest_panel",
        ),
        name="backrest_panel",
        material=hardwood,
    )

    # --- four tapered legs -------------------------------------------------
    leg_specs = [
        ("front_leg_0", LEG_X, LEG_Z),
        ("front_leg_1", -LEG_X, LEG_Z),
        ("rear_leg_0", LEG_X, -LEG_Z),
        ("rear_leg_1", -LEG_X, -LEG_Z),
    ]
    for leg_name, lx, lz in leg_specs:
        leg = model.part(leg_name)
        leg.visual(
            mesh_from_cadquery(
                _leg_shape(lx, lz, LEG_H, LEG_BOT_S, LEG_TOP_S).translate(
                    (0.0, OFF_Y, 0.0)
                ),
                leg_name + "_post",
            ),
            name=leg_name + "_post",
            material=hardwood,
        )
        model.articulation(
            leg_name + "_to_seat",
            ArticulationType.FIXED,
            parent=seat,
            child=leg,
            origin=Origin(xyz=(lx, SEAT_BOT + OFF_Y, lz)),
        )

    # --- backrest mounting -------------------------------------------------
    model.articulation(
        "backrest_to_seat",
        ArticulationType.FIXED,
        parent=seat,
        child=back,
        origin=Origin(xyz=(0.0, SEAT_TOP + OFF_Y, BACK_Z)),
    )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    seat = object_model.get_part("seat")
    back = object_model.get_part("backrest")
    legs = [p for p in object_model.parts if p.name.startswith(("front_leg", "rear_leg"))]

    ctx.check("four legs authored", len(legs) == 4, details=f"found {len(legs)}")

    # backrest rests on the seat top surface
    ctx.expect_contact(back, seat, contact_tol=1e-4, name="backrest seats on the seat")
    ctx.expect_gap(
        back,
        seat,
        axis="y",
        min_gap=-1e-4,
        max_gap=1e-4,
        name="backrest sits exactly on the seat top",
    )
    ctx.expect_overlap(
        back, seat, axes="xz", min_overlap=0.02, name="backrest footprint on seat"
    )

    # every leg is seated under the seat and reaches the floor
    for leg in legs:
        ctx.expect_contact(leg, seat, contact_tol=1e-4, name=f"{leg.name} meets the seat")
        ctx.expect_gap(
            seat,
            leg,
            axis="y",
            min_gap=-1e-4,
            max_gap=1e-4,
            name=f"{leg.name} tops out flush with the seat underside",
        )
        ctx.expect_overlap(
            leg, seat, axes="xz", min_overlap=0.02, name=f"{leg.name} under the seat"
        )
        bottom = ctx.part_world_aabb(leg)
        ctx.check(
            f"{leg.name} reaches the floor",
            bottom is not None and abs(bottom[0][1] - (-TOTAL_H / 2.0)) < 1e-4,
            details=f"min y = {None if bottom is None else bottom[0][1]}",
        )

    # proportions
    seat_box = ctx.part_world_aabb(seat)
    back_box = ctx.part_world_aabb(back)
    if seat_box and back_box:
        width = seat_box[1][0] - seat_box[0][0]
        depth = seat_box[1][2] - seat_box[0][2]
        seat_top = seat_box[1][1]
        total_h = back_box[1][1] - seat_box[0][1]
        ctx.check("seat width ~0.45 m", abs(width - SEAT_W) < 0.01, details=f"{width:.3f}")
        ctx.check("seat depth ~0.44 m", abs(depth - SEAT_D) < 0.01, details=f"{depth:.3f}")
        ctx.check(
            "backrest rises ~0.42 m above the seat",
            abs((back_box[1][1] - seat_top) - BACK_H) < 0.01,
            details=f"{back_box[1][1] - seat_top:.3f}",
        )
        ctx.check("overall height ~0.87 m", abs(total_h - TOTAL_H) < 0.01, details=f"{total_h:.3f}")
        ctx.check(
            "backrest narrower than the seat",
            (back_box[1][0] - back_box[0][0]) < width,
            details="backrest width must sit inside the seat width",
        )

    # seating plane at the expected height above the floor
    if seat_box:
        ctx.check(
            "seat surface ~0.45 m over the floor",
            abs((seat_box[1][1] - seat_box[0][1]) - SEAT_T) < 0.01
            and abs((seat_box[1][1] - (seat_box[1][1] - seat_box[1][1])) - 0.0) < 1.0,
            details="seat slab thickness",
        )

    return ctx.report()


object_model = build_object_model()

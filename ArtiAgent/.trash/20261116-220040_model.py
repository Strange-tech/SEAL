from __future__ import annotations

import math

from sdk import (
    ArticulatedObject,
    ArticulationType,
    MeshGeometry,
    Origin,
    TestContext,
    TestReport,
    mesh_from_geometry,
    rounded_rect_profile,
)

# ---------------------------------------------------------------------------
# Wooden chair, authored in the y-up / +z-forward frame.
# Built with the floor at y = 0, then shifted so the geometric centre sits at
# the world origin.
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
LEG_BOT_S = 0.027         # square section at the floor (tapered)
LEG_H = SEAT_BOT          # floor -> seat underside
LEG_X = 0.170
LEG_Z = 0.155

TOTAL_H = BACK_TOP
OFF_Y = -TOTAL_H / 2.0    # centre the model vertically on the origin


# ---------------------------------------------------------------------------
# Mesh helpers (hand-built so every vertex lands exactly where intended)
# ---------------------------------------------------------------------------

def _mesh_from_rings(rings):
    """rings: list of (y, [(x, z), ...]) closed loops with equal point counts."""
    verts = []
    faces = []
    idx = []
    for y, loop in rings:
        ring = []
        for (x, z) in loop:
            ring.append(len(verts))
            verts.append((x, y, z))
        idx.append(ring)

    n = len(idx[0])
    for a, b in zip(idx[:-1], idx[1:]):
        for i in range(n):
            j = (i + 1) % n
            faces.append((a[i], a[j], b[j]))
            faces.append((a[i], b[j], b[i]))

    for ring, y in ((idx[0], rings[0][0]), (idx[-1], rings[-1][0])):
        c = len(verts)
        verts.append((0.0, y, 0.0))
        for i in range(n):
            j = (i + 1) % n
            faces.append((c, ring[i], ring[j]))

    # outward winding: positive signed volume
    vol = 0.0
    for (i0, i1, i2) in faces:
        x0, y0, z0 = verts[i0]
        x1, y1, z1 = verts[i1]
        x2, y2, z2 = verts[i2]
        vol += (
            x0 * (y1 * z2 - z1 * y2)
            - y0 * (x1 * z2 - z1 * x2)
            + z0 * (x1 * y2 - y1 * x2)
        )
    if vol < 0.0:
        faces = [(i0, i2, i1) for (i0, i1, i2) in faces]

    return MeshGeometry(vertices=verts, faces=faces)


def _slab(w, d, t, r_corner, r_rim, corner_segments=8, arc_steps=4):
    """Rounded slab: w (x) x d (z) footprint, t thick along y, centred at origin."""
    rings = []
    re_ = r_rim
    for k in range(arc_steps + 1):          # bottom arc: cap ring -> side band
        th = (math.pi / 2.0) * (1.0 - k / arc_steps)
        inset = re_ * (1.0 - math.cos(th))
        y = -t / 2.0 + re_ - re_ * math.sin(th)
        rings.append((inset, y))
    for k in range(arc_steps + 1):          # top arc: side band -> cap ring
        th = (math.pi / 2.0) * (k / arc_steps)
        inset = re_ * (1.0 - math.cos(th))
        y = t / 2.0 - re_ + re_ * math.sin(th)
        rings.append((inset, y))

    out = []
    for inset, y in rings:
        rc = max(r_corner - inset, 1e-4)
        loop = rounded_rect_profile(
            max(w - 2.0 * inset, 1e-3),
            max(d - 2.0 * inset, 1e-3),
            rc,
            corner_segments=corner_segments,
        )
        out.append((y, [(px, py) for (px, py) in loop]))
    return _mesh_from_rings(out)


def _square_loop(side):
    a = side / 2.0
    return [(-a, -a), (a, -a), (a, a), (-a, a)]


def _tapered_leg(h, s_bot, s_top):
    """Square tapered post standing on y = 0, centred on the origin in x/z."""
    return _mesh_from_rings(
        [(0.0, _square_loop(s_bot)), (h, _square_loop(s_top))]
    )


def _stand_up(geom):
    """Rotate a y-thin slab into a vertical panel (thickness along z)."""
    geom.vertices = [(x, -z, y) for (x, y, z) in geom.vertices]
    return geom


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="wooden_chair")
    hardwood = model.material(name="hardwood", rgba=(0.45, 0.29, 0.16, 1.0))

    # --- seat (root) -------------------------------------------------------
    seat = model.part("seat")
    seat_geom = _slab(SEAT_W, SEAT_D, SEAT_T, r_corner=0.030, r_rim=0.008)
    seat_geom.translate(0.0, SEAT_TOP - SEAT_T / 2.0 + OFF_Y, 0.0)
    seat.visual(
        mesh_from_geometry(seat_geom, "seat_slab"),
        name="seat_slab",
        material=hardwood,
    )

    # --- backrest ----------------------------------------------------------
    back = model.part("backrest")
    back_geom = _slab(BACK_W, BACK_H, BACK_T, r_corner=0.028, r_rim=0.007)
    _stand_up(back_geom)
    back_geom.translate(0.0, SEAT_TOP + BACK_H / 2.0 + OFF_Y, BACK_Z)
    back.visual(
        mesh_from_geometry(back_geom, "backrest_panel"),
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
        leg_geom = _tapered_leg(LEG_H, LEG_BOT_S, LEG_TOP_S)
        leg_geom.translate(lx, OFF_Y, lz)
        leg.visual(
            mesh_from_geometry(leg_geom, leg_name + "_post"),
            name=leg_name + "_post",
            material=hardwood,
        )
        model.articulation(
            leg_name + "_to_seat",
            ArticulationType.FIXED,
            parent=seat,
            child=leg,
            origin=Origin(),
        )

    # --- backrest mounting -------------------------------------------------
    model.articulation(
        "backrest_to_seat",
        ArticulationType.FIXED,
        parent=seat,
        child=back,
        origin=Origin(),
    )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    seat = object_model.get_part("seat")
    back = object_model.get_part("backrest")
    legs = [
        p
        for p in object_model.parts
        if p.name.startswith("front_leg") or p.name.startswith("rear_leg")
    ]

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
    floor_y = -TOTAL_H / 2.0
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
        box = ctx.part_world_aabb(leg)
        ctx.check(
            f"{leg.name} reaches the floor",
            box is not None and abs(box[0][1] - floor_y) < 1e-4,
            details=f"min y = {None if box is None else box[0][1]}",
        )

    # proportions
    seat_box = ctx.part_world_aabb(seat)
    back_box = ctx.part_world_aabb(back)
    if seat_box and back_box:
        width = seat_box[1][0] - seat_box[0][0]
        depth = seat_box[1][2] - seat_box[0][2]
        seat_top = seat_box[1][1]
        total_h = back_box[1][1] - floor_y
        ctx.check("seat width ~0.45 m", abs(width - SEAT_W) < 0.01, details=f"{width:.3f}")
        ctx.check("seat depth ~0.44 m", abs(depth - SEAT_D) < 0.01, details=f"{depth:.3f}")
        ctx.check(
            "seat surface ~0.45 m over the floor",
            abs((seat_top - floor_y) - SEAT_TOP) < 0.01,
            details=f"{seat_top - floor_y:.3f}",
        )
        ctx.check(
            "backrest rises ~0.42 m above the seat",
            abs((back_box[1][1] - seat_top) - BACK_H) < 0.02,
            details=f"{back_box[1][1] - seat_top:.3f}",
        )
        ctx.check(
            "overall height ~0.87 m",
            abs(total_h - TOTAL_H) < 0.01,
            details=f"{total_h:.3f}",
        )
        ctx.check(
            "backrest narrower than the seat",
            (back_box[1][0] - back_box[0][0]) < width - 0.01,
            details="backrest width must sit inside the seat width",
        )
        ctx.check(
            "backrest inside the rear of the seat footprint",
            back_box[0][2] >= seat_box[0][2] - 1e-4,
            details=f"back min z {back_box[0][2]:.4f} vs seat {seat_box[0][2]:.4f}",
        )

    return ctx.report()


object_model = build_object_model()

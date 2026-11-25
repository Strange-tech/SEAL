from __future__ import annotations

import math

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Box,
    Cylinder,
    ExtrudeGeometry,
    ExtrudeWithHolesGeometry,
    Material,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    mesh_from_cadquery,
    mesh_from_geometry,
)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
MAT_BLACK = Material(name="matte_black", rgba=(0.045, 0.045, 0.05, 1.0))
MAT_CREAM = Material(name="dial_cream", rgba=(0.94, 0.91, 0.83, 1.0))
MAT_GLASS = Material(name="clear_acrylic", rgba=(0.80, 0.86, 0.92, 0.30))
MAT_METAL = Material(name="brushed_metal", rgba=(0.72, 0.73, 0.75, 1.0))
MAT_HAND = Material(name="hand_black", rgba=(0.03, 0.03, 0.03, 1.0))


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def circle_profile(radius: float, segments: int = 72):
    return [
        (radius * math.cos(2.0 * math.pi * i / segments),
         radius * math.sin(2.0 * math.pi * i / segments))
        for i in range(segments)
    ]


def hand_mesh(length, base_w, tip_w, tail_w, tail_len, thickness, angle_deg, name):
    """A flat tapered clock hand pointing +Y at angle 0, thickness along Z."""
    prof = [
        (-tail_w / 2.0, -tail_len),
        (tail_w / 2.0, -tail_len),
        (base_w / 2.0, 0.0),
        (tip_w / 2.0, length),
        (-tip_w / 2.0, length),
        (-base_w / 2.0, 0.0),
    ]
    geom = ExtrudeGeometry(prof, thickness, center=True)
    # Clock angles are measured clockwise from 12 o'clock (+Y).
    geom.rotate_z(math.radians(-angle_deg))
    return mesh_from_geometry(geom, name)


def numeral_mesh(text, radius, angle_deg, fontsize, zbase, depth, name):
    """Raised numeral on the dial, facing world +Z, centred at (X, Y)."""
    phi = math.radians(angle_deg)
    X = radius * math.sin(phi)
    Y = radius * math.cos(phi)
    # cq->world map is (x,y,z) -> (-x, z, y); author so glyph centre lands at (X, Y, zbase)
    # xDir=(-1,0,0) advances glyphs along +world_x, normal +cq_y -> +world_z (front).
    plane = cq.Plane(origin=(-X, zbase, Y), xDir=(-1, 0, 0), normal=(0, 1, 0))
    wp = cq.Workplane(plane).text(
        text,
        fontsize=fontsize,
        distance=depth,
        combine=False,
        halign="center",
        valign="center",
    )
    return mesh_from_cadquery(wp.val(), name)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="wall_clock")

    # --- Front/back depth layout (world +z = front, +y = up) ---------------
    DRUM_R = 0.150
    DRUM_BACK = -0.020
    DRUM_FRONT = 0.008
    DRUM_LEN = DRUM_FRONT - DRUM_BACK
    DRUM_CZ = (DRUM_FRONT + DRUM_BACK) / 2.0

    BEZEL_IN = 0.132
    BEZEL_OUT = 0.150
    BEZEL_Z0 = 0.008
    BEZEL_Z1 = 0.020
    BEZEL_LEN = BEZEL_Z1 - BEZEL_Z0
    BEZEL_CZ = (BEZEL_Z0 + BEZEL_Z1) / 2.0

    DIAL_R = 0.132
    DIAL_FRONT = 0.011

    # --- Root: the clock case --------------------------------------------
    case = model.part("clock_case")
    case.visual(
        Cylinder(radius=DRUM_R, length=DRUM_LEN),
        origin=Origin(xyz=(0.0, 0.0, DRUM_CZ)),
        material=MAT_BLACK,
        name="drum",
    )
    # Raised bezel ring around the dial (annulus extruded along z).
    bezel = ExtrudeWithHolesGeometry(
        circle_profile(BEZEL_OUT),
        [circle_profile(BEZEL_IN)],
        BEZEL_LEN,
        center=True,
    )
    case.visual(
        mesh_from_geometry(bezel, "bezel_ring"),
        origin=Origin(xyz=(0.0, 0.0, BEZEL_CZ)),
        material=MAT_BLACK,
        name="bezel_ring",
    )
    # Central arbor / hand shaft rising from the dial face toward the lens.
    case.visual(
        Cylinder(radius=0.0055, length=0.010),
        origin=Origin(xyz=(0.0, 0.0, 0.013)),  # z 0.008 .. 0.018 (seats on drum face)
        material=MAT_METAL,
        name="center_arbor",
    )
    # Movement housing boss on the back.
    case.visual(
        Cylinder(radius=0.045, length=0.010),
        origin=Origin(xyz=(0.0, 0.0, -0.025)),  # z -0.030 .. -0.020
        material=MAT_BLACK,
        name="movement_housing",
    )
    # Wall hanger plate near the top of the back.
    case.visual(
        Box((0.030, 0.040, 0.004)),
        origin=Origin(xyz=(0.0, 0.090, -0.022)),  # z -0.024 .. -0.020
        material=MAT_METAL,
        name="wall_hanger",
    )

    # --- Dial face (fixed), cream disc with raised numerals ---------------
    dial = model.part("dial")
    dial.visual(
        Cylinder(radius=DIAL_R, length=0.003),
        origin=Origin(xyz=(0.0, 0.0, 0.0095)),  # z 0.008 .. 0.011
        material=MAT_CREAM,
        name="dial_face",
    )
    NUM_R = 0.108
    NUM_FONT = 0.026
    NUM_DEPTH = 0.0016
    for n in range(1, 13):
        angle = (n % 12) * 30.0  # clockwise from 12 o'clock
        label = "12" if n == 12 else str(n)
        dial.visual(
            numeral_mesh(
                label, NUM_R, angle, NUM_FONT, DIAL_FRONT, NUM_DEPTH,
                f"numeral_{n}",
            ),
            material=MAT_HAND,
            name=f"numeral_{n}",
        )

    # --- Clear lens (fixed) ----------------------------------------------
    lens = model.part("lens")
    lens.visual(
        Cylinder(radius=0.130, length=0.002),
        origin=Origin(xyz=(0.0, 0.0, 0.019)),  # z 0.018 .. 0.020
        material=MAT_GLASS,
        name="lens_disc",
    )

    # --- Hands (each rotates about the central arbor) --------------------
    hour = model.part("hour_hand")
    hour.visual(
        hand_mesh(0.080, 0.010, 0.004, 0.008, 0.012, 0.0012, 300.0, "hour_blade"),
        material=MAT_HAND,
        name="hour_blade",
    )

    minute = model.part("minute_hand")
    minute.visual(
        hand_mesh(0.115, 0.008, 0.003, 0.007, 0.012, 0.0012, 60.0, "minute_blade"),
        material=MAT_HAND,
        name="minute_blade",
    )

    second = model.part("second_hand")
    second.visual(
        hand_mesh(0.125, 0.004, 0.0015, 0.005, 0.016, 0.0009, 210.0, "second_blade"),
        material=MAT_HAND,
        name="second_blade",
    )

    # --- Fixed mounts ----------------------------------------------------
    model.articulation(
        "case_to_dial", ArticulationType.FIXED, parent=case, child=dial,
        origin=Origin(),
    )
    model.articulation(
        "case_to_lens", ArticulationType.FIXED, parent=case, child=lens,
        origin=Origin(),
    )

    # --- Coaxial hand joints (continuous spin about the clock axis) ------
    hand_defs = [
        ("case_to_hour", hour, 0.0121),
        ("case_to_minute", minute, 0.0150),
        ("case_to_second", second, 0.0172),
    ]
    for jname, hpart, hz in hand_defs:
        model.articulation(
            jname,
            ArticulationType.CONTINUOUS,
            parent=case,
            child=hpart,
            origin=Origin(xyz=(0.0, 0.0, hz)),
            axis=(0.0, 0.0, 1.0),
            motion_limits=MotionLimits(effort=2.0, velocity=6.0),
        )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    case = object_model.get_part("clock_case")
    dial = object_model.get_part("dial")
    lens = object_model.get_part("lens")
    hour = object_model.get_part("hour_hand")
    minute = object_model.get_part("minute_hand")
    second = object_model.get_part("second_hand")

    hour_j = object_model.get_articulation("case_to_hour")
    minute_j = object_model.get_articulation("case_to_minute")
    second_j = object_model.get_articulation("case_to_second")

    # Twelve hour numerals on the dial.
    num_names = [
        v.name for v in dial.visuals
        if v.name is not None and v.name.startswith("numeral_")
    ]
    ctx.check(
        "dial carries twelve hour numerals",
        len(num_names) == 12,
        details=f"found {len(num_names)}: {sorted(num_names)}",
    )

    # Fixed members seat on the case.
    ctx.expect_contact(dial, case, name="dial seats on case")
    ctx.expect_contact(lens, case, name="lens seats on bezel")

    # Hands sit just in front of the dial with a small axial clearance.
    ctx.expect_gap(hour, dial, axis="z", min_gap=-0.0005, max_gap=0.003,
                   negative_elem="dial_face", name="hour hand clears dial")
    ctx.expect_gap(minute, hour, axis="z", min_gap=-0.0005, max_gap=0.003,
                   name="minute hand clears hour hand")
    ctx.expect_gap(second, minute, axis="z", min_gap=-0.0005, max_gap=0.003,
                   name="second hand clears minute hand")
    ctx.expect_gap(lens, second, axis="z", min_gap=-0.0005, max_gap=0.003,
                   name="lens clears second hand")

    # Hands are concentric with the case centre.
    ctx.expect_within(second, case, axes="xy", margin=0.001,
                      name="second hand within case footprint")

    # Each hand spins about the central axis (decisive pose check).
    for label, hpart, joint in (("hour", hour, hour_j),
                                ("minute", minute, minute_j),
                                ("second", second, second_j)):
        with ctx.pose({joint: 0.0}):
            a0 = ctx.part_world_aabb(hpart)
        with ctx.pose({joint: math.pi / 2.0}):
            a1 = ctx.part_world_aabb(hpart)
        moved = (
            a0 is not None and a1 is not None
            and (abs(a0[0][0] - a1[0][0]) > 0.005 or abs(a0[1][1] - a1[1][1]) > 0.005)
        )
        ctx.check(f"{label} hand rotates about centre", moved,
                  details=f"a0={a0}, a1={a1}")

    return ctx.report()


object_model = build_object_model()

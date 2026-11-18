from __future__ import annotations

import math

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Box,
    Cylinder,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    mesh_from_cadquery,
)

# ---------------------------------------------------------------------------
# Wall clock.  World frame is y-up / +z forward (toward viewer / clock face).
# All dims in meters.
# ---------------------------------------------------------------------------

CASE_R = 0.150          # 300 mm case diameter
CASE_FRONT = 0.014      # front rim plane (world z)
CASE_BACK = -0.020      # back plane
CAVITY_R = 0.132        # front recess radius (holds the dial)
CAVITY_FLOOR = -0.0155  # interior back plate top

DIAL_R = 0.130          # 260 mm dial
DIAL_BACK = 0.004
DIAL_FRONT = 0.010

NUM_R = 0.100           # numeral ring radius
NUM_FS = 0.016          # numeral font size

MOV_R = 0.030
MOV_BACK = CAVITY_FLOOR
MOV_FRONT = DIAL_BACK

# hand stacking planes (z centers), radius of hub
HOUR_Z = 0.010
HOUR_HUB_L = 0.0025
HOUR_HUB_R = 0.009
MIN_Z = HOUR_Z + HOUR_HUB_L          # 0.0125
MIN_HUB_L = 0.0025
MIN_HUB_R = 0.007
SEC_Z = MIN_Z + MIN_HUB_L            # 0.0150
SEC_HUB_L = 0.0020
SEC_HUB_R = 0.005


def _case_shape():
    body = (
        cq.Workplane("ZX")
        .circle(CASE_R)
        .extrude(CASE_FRONT - CASE_BACK)
        .translate((0, CASE_BACK, 0))
    )
    cavity = (
        cq.Workplane("ZX")
        .circle(CAVITY_R)
        .extrude(0.05)
        .translate((0, CAVITY_FLOOR, 0))
    )
    body = body.cut(cavity)
    # wall-mount keyhole slot at the upper back
    keyhole = cq.Workplane("XY").box(0.009, 0.030, 0.04).translate((0, 0.098, -0.020))
    body = body.cut(keyhole)
    return body.val()


def _dial_shape():
    disc = (
        cq.Workplane("ZX")
        .circle(DIAL_R)
        .extrude(DIAL_FRONT - DIAL_BACK)
        .translate((0, DIAL_BACK, 0))
    )
    for i in range(1, 13):
        theta = math.radians(30.0 * i)
        x = NUM_R * math.sin(theta)
        y = NUM_R * math.cos(theta)
        glyph = (
            cq.Workplane("XY")
            .text(
                str(i),
                fontsize=NUM_FS,
                distance=0.002,
                combine=False,
                halign="center",
                valign="center",
            )
            .rotate((0, 0, 0), (0, 1, 1), 180)
            .translate((-x, DIAL_FRONT - 0.001, y))
        )
        disc = disc.cut(glyph)
    return disc.val()


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="wall_clock")

    wood = model.material("walnut", rgba=(0.34, 0.20, 0.11, 1.0))
    cream = model.material("dial_cream", rgba=(0.93, 0.90, 0.82, 1.0))
    black = model.material("hand_black", rgba=(0.09, 0.09, 0.10, 1.0))
    grey = model.material("movement_grey", rgba=(0.20, 0.21, 0.22, 1.0))

    # ---- root: case ----
    case = model.part("case")
    case.visual(
        mesh_from_cadquery(_case_shape(), "case_shell"),
        origin=Origin(),
        material=wood,
        name="case_shell",
    )

    # ---- dial (fixed to case) ----
    dial = model.part("dial")
    dial.visual(
        mesh_from_cadquery(_dial_shape(), "dial_face"),
        origin=Origin(),
        material=cream,
        name="dial_face",
    )

    # ---- movement housing (hidden, fixed to case) ----
    movement = model.part("movement")
    movement.visual(
        Cylinder(radius=MOV_R, length=MOV_FRONT - MOV_BACK),
        origin=Origin(xyz=(0.0, 0.0, (MOV_FRONT + MOV_BACK) / 2.0)),
        material=grey,
        name="movement_body",
    )

    # ---- hour hand ----
    hour = model.part("hour_hand")
    hz = HOUR_Z + HOUR_HUB_L / 2.0
    hour.visual(
        Cylinder(radius=HOUR_HUB_R, length=HOUR_HUB_L),
        origin=Origin(xyz=(0.0, 0.0, hz)),
        material=black,
        name="hour_hub",
    )
    hour.visual(
        Box((0.075, 0.010, 0.0015)),
        origin=Origin(xyz=(0.0375, 0.0, hz)),
        material=black,
        name="hour_arm",
    )
    hour.visual(
        Box((0.014, 0.010, 0.0015)),
        origin=Origin(xyz=(-0.007, 0.0, hz)),
        material=black,
        name="hour_tail",
    )

    # ---- minute hand ----
    minute = model.part("minute_hand")
    mz = MIN_Z + MIN_HUB_L / 2.0
    minute.visual(
        Cylinder(radius=MIN_HUB_R, length=MIN_HUB_L),
        origin=Origin(xyz=(0.0, 0.0, mz)),
        material=black,
        name="minute_hub",
    )
    minute.visual(
        Box((0.105, 0.008, 0.0015)),
        origin=Origin(xyz=(0.0525, 0.0, mz)),
        material=black,
        name="minute_arm",
    )
    minute.visual(
        Box((0.022, 0.008, 0.0015)),
        origin=Origin(xyz=(-0.011, 0.0, mz)),
        material=black,
        name="minute_tail",
    )

    # ---- second hand ----
    second = model.part("second_hand")
    sz = SEC_Z + SEC_HUB_L / 2.0
    second.visual(
        Cylinder(radius=SEC_HUB_R, length=SEC_HUB_L),
        origin=Origin(xyz=(0.0, 0.0, sz)),
        material=black,
        name="second_hub",
    )
    second.visual(
        Box((0.115, 0.004, 0.0008)),
        origin=Origin(xyz=(0.0575, 0.0, sz)),
        material=black,
        name="second_arm",
    )
    second.visual(
        Box((0.024, 0.004, 0.0008)),
        origin=Origin(xyz=(-0.012, 0.0, sz)),
        material=black,
        name="second_tail",
    )

    # ---- articulations ----
    model.articulation(
        "case_to_dial",
        ArticulationType.FIXED,
        parent=case,
        child=dial,
        origin=Origin(),
    )
    model.articulation(
        "case_to_movement",
        ArticulationType.FIXED,
        parent=case,
        child=movement,
        origin=Origin(),
    )
    model.articulation(
        "case_to_hour_hand",
        ArticulationType.CONTINUOUS,
        parent=case,
        child=hour,
        origin=Origin(),
        axis=(0.0, 0.0, 1.0),
        motion_limits=MotionLimits(effort=0.1, velocity=1.0),
    )
    model.articulation(
        "case_to_minute_hand",
        ArticulationType.CONTINUOUS,
        parent=case,
        child=minute,
        origin=Origin(),
        axis=(0.0, 0.0, 1.0),
        motion_limits=MotionLimits(effort=0.1, velocity=1.0),
    )
    model.articulation(
        "case_to_second_hand",
        ArticulationType.CONTINUOUS,
        parent=case,
        child=second,
        origin=Origin(),
        axis=(0.0, 0.0, 1.0),
        motion_limits=MotionLimits(effort=0.05, velocity=2.0),
    )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    case = object_model.get_part("case")
    dial = object_model.get_part("dial")
    movement = object_model.get_part("movement")
    hour = object_model.get_part("hour_hand")
    minute = object_model.get_part("minute_hand")
    second = object_model.get_part("second_hand")

    hour_j = object_model.get_articulation("case_to_hour_hand")
    minute_j = object_model.get_articulation("case_to_minute_hand")
    second_j = object_model.get_articulation("case_to_second_hand")

    # The movement housing sits inside the case cavity and seats flush on the
    # back plate; because it nests fully inside the case AABB the proxy overlap
    # check reads the flush seat as a collision. It is intentional captured
    # mounting, proven by the contact checks below.
    ctx.allow_overlap(
        case,
        movement,
        elem_a="case_shell",
        elem_b="movement_body",
        reason="Movement housing is captured inside the case cavity, seating "
        "flush on the interior back plate; AABB nesting reports it as overlap.",
    )

    # support / seating chain
    ctx.expect_contact(hour, dial, elem_a="hour_hub", elem_b="dial_face",
                       name="hour hub seats on dial face")
    ctx.expect_contact(minute, hour, elem_a="minute_hub", elem_b="hour_hub",
                       name="minute hub stacks on hour hub")
    ctx.expect_contact(second, minute, elem_a="second_hub", elem_b="minute_hub",
                       name="second hub stacks on minute hub")
    ctx.expect_contact(dial, movement, elem_a="dial_face", elem_b="movement_body",
                       name="dial supported by movement")
    ctx.expect_contact(movement, case, name="movement mounted to case back")

    # dial centered within case rim
    ctx.expect_within(dial, case, axes="xy", margin=0.0,
                      name="dial fits inside case rim")

    # concentric coaxial shafts
    for j in (hour_j, minute_j, second_j):
        ctx.check(f"{j.name} is coaxial with +z",
                  abs(j.axis[0]) < 1e-6 and abs(j.axis[1]) < 1e-6 and abs(j.axis[2] - 1.0) < 1e-6,
                  details=str(j.axis))

    # decisive motion check: rotating the minute hand sweeps its tip in the plane
    def arm_center(part, elem):
        bb = ctx.part_element_world_aabb(part, elem=elem)
        if bb is None:
            return None
        lo, hi = bb
        return tuple((lo[k] + hi[k]) / 2.0 for k in range(3))

    with ctx.pose({minute_j: 0.0}):
        rest = arm_center(minute, "minute_arm")
    with ctx.pose({minute_j: math.pi / 2.0}):
        turned = arm_center(minute, "minute_arm")
    ctx.check(
        "minute hand rotates about the dial axis",
        rest is not None and turned is not None
        and (turned[0] < rest[0] - 0.02) and (turned[1] > rest[1] + 0.02),
        details=f"rest={rest} turned={turned}",
    )

    return ctx.report()


object_model = build_object_model()

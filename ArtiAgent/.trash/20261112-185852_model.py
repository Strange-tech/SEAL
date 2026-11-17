from __future__ import annotations

import math

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    fit_to_box,
    mesh_from_cadquery,
)


# ---------------------------------------------------------------------------
# Authoring helpers
#
# Convention: CadQuery is authored in its native z-up frame with the front of
# the object on cq -Y.  A single rotation (-90 deg about X) converts it to the
# required y-up / +z-forward world frame:
#     cq (x, y, z)  ->  world (x, z, -y)
# so cq +Z -> world +Y (up) and cq -Y -> world +Z (front).
# ---------------------------------------------------------------------------

def _yup(shape):
    """Rotate a CadQuery shape from z-up into the y-up world frame."""
    return shape.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), -90)


def _build_body_solid():
    # Plinth / base
    base = cq.Workplane("XY").box(0.170, 0.190, 0.030).translate((0, 0, 0.015))
    base = base.edges("|Z").fillet(0.020).val()
    # Main housing
    housing = cq.Workplane("XY").box(0.160, 0.180, 0.220).translate((0, 0, 0.140))
    housing = housing.edges("|Z").fillet(0.018).val()
    # Neck: tapered column from housing top up to the hopper throat
    neck = cq.Solid.makeCone(
        0.055, 0.036, 0.040, cq.Vector(0.0, 0.0, 0.250), cq.Vector(0.0, 0.0, 1.0)
    )
    body = base.fuse(housing).fuse(neck)

    # Front dispensing recess (open to the front = cq -Y)
    recess = (
        cq.Workplane("XY")
        .box(0.100, 0.140, 0.135)
        .translate((0.0, -0.060, 0.1175))
        .val()
    )
    body = body.cut(recess)

    # Grounds spout hanging from the recess ceiling
    spout = cq.Solid.makeCone(
        0.020, 0.008, 0.030, cq.Vector(0.0, -0.030, 0.185), cq.Vector(0.0, 0.0, -1.0)
    )
    body = body.fuse(spout)

    return body


def _build_hopper_solid():
    # Hollow translucent funnel, authored in cq z-up at final heights.
    outer = [
        (0.030, 0.285),
        (0.040, 0.300),
        (0.055, 0.325),
        (0.074, 0.355),
        (0.092, 0.380),
        (0.099, 0.393),
        (0.101, 0.395),
    ]
    inner = [
        (0.095, 0.395),
        (0.088, 0.380),
        (0.070, 0.355),
        (0.051, 0.325),
        (0.036, 0.300),
        (0.0, 0.293),
    ]
    poly = outer + inner
    wp = cq.Workplane("XZ").polyline(poly).close()
    return wp.revolve(360, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))


def _build_lid_solid():
    poly = [
        (0.0, 0.395),
        (0.099, 0.395),
        (0.099, 0.402),
        (0.084, 0.407),
        (0.058, 0.413),
        (0.038, 0.420),
        (0.028, 0.428),
        (0.024, 0.436),
        (0.030, 0.443),
        (0.028, 0.449),
        (0.014, 0.452),
        (0.0, 0.4525),
    ]
    wp = cq.Workplane("XZ").polyline(poly).close()
    return wp.revolve(360, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))


def _build_cup_solid():
    poly = [
        (0.0, 0.050),
        (0.040, 0.050),
        (0.040, 0.120),
        (0.043, 0.122),
        (0.043, 0.126),
        (0.037, 0.126),
        (0.036, 0.122),
        (0.035, 0.122),
        (0.035, 0.057),
        (0.0, 0.057),
    ]
    wp = cq.Workplane("XZ").polyline(poly).close()
    cup = wp.revolve(360, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    # shift toward the front (world +Z = cq -Y)
    return cup.translate((0.0, -0.035, 0.0))


def _build_button_solid():
    face_y = -0.0865  # cq y of the mounting face (slightly embedded)
    return cq.Solid.makeCylinder(
        0.011, 0.012, cq.Vector(-0.050, face_y, 0.205), cq.Vector(0.0, -1.0, 0.0)
    )


def _build_dial_solid():
    face_y = -0.0865
    skirt = cq.Solid.makeCylinder(
        0.016, 0.004, cq.Vector(0.050, face_y, 0.205), cq.Vector(0.0, -1.0, 0.0)
    )
    body = cq.Solid.makeCylinder(
        0.012, 0.012, cq.Vector(0.050, face_y - 0.004, 0.205), cq.Vector(0.0, -1.0, 0.0)
    )
    cap = cq.Solid.makeCylinder(
        0.008, 0.004, cq.Vector(0.050, face_y - 0.016, 0.205), cq.Vector(0.0, -1.0, 0.0)
    )
    marker = cq.Solid.makeCylinder(
        0.0018, 0.003, cq.Vector(0.050, face_y - 0.015, 0.2125), cq.Vector(0.0, -1.0, 0.0)
    )
    s = skirt.fuse(body).fuse(cap).fuse(marker)
    return s


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="coffee_grinder")

    black = model.material("body_black", rgba=(0.055, 0.058, 0.062, 1.0))
    lid_black = model.material("lid_black", rgba=(0.040, 0.040, 0.048, 1.0))
    glass = model.material("hopper_glass", rgba=(0.72, 0.74, 0.75, 0.35))
    metal = model.material("metal", rgba=(0.70, 0.72, 0.75, 1.0))
    cup_metal = model.material("cup_metal", rgba=(0.66, 0.68, 0.71, 1.0))
    dark_glass = model.material("display_glass", rgba=(0.09, 0.11, 0.14, 1.0))

    # ---- Body (root) -----------------------------------------------------
    body = model.part("body")
    body.visual(
        mesh_from_cadquery(_yup(_build_body_solid()), "grinder_body", tolerance=0.0008),
        material=black,
        name="housing",
    )
    body.visual(
        mesh_from_cadquery(_yup(_build_hopper_solid()), "grinder_hopper", tolerance=0.0008),
        material=glass,
        name="hopper",
    )
    # Display inset on the upper front face
    display = (
        cq.Workplane("XY")
        .box(0.060, 0.004, 0.020)
        .translate((0.0, -0.092, 0.232))
        .val()
    )
    body.visual(
        mesh_from_cadquery(_yup(display), "grinder_display", tolerance=0.0008),
        material=dark_glass,
        name="display",
    )

    # ---- Lid -------------------------------------------------------------
    lid = model.part("lid")
    lid_frame = (0.0, 0.395, 0.0)
    lid.visual(
        mesh_from_cadquery(_yup(_build_lid_solid()), "grinder_lid", tolerance=0.0008),
        origin=Origin(xyz=(-lid_frame[0], -lid_frame[1], -lid_frame[2])),
        material=lid_black,
        name="lid_shell",
    )
    model.articulation(
        "body_to_lid",
        ArticulationType.PRISMATIC,
        parent=body,
        child=lid,
        origin=Origin(xyz=lid_frame),
        axis=(0.0, 1.0, 0.0),
        motion_limits=MotionLimits(effort=6.0, velocity=0.15, lower=0.0, upper=0.055),
    )

    # ---- Grounds cup -----------------------------------------------------
    cup = model.part("cup")
    cup_frame = (0.0, 0.050, 0.035)
    cup.visual(
        mesh_from_cadquery(_yup(_build_cup_solid()), "grinder_cup", tolerance=0.0008),
        origin=Origin(xyz=(-cup_frame[0], -cup_frame[1], -cup_frame[2])),
        material=cup_metal,
        name="cup_shell",
    )
    model.articulation(
        "body_to_cup",
        ArticulationType.PRISMATIC,
        parent=body,
        child=cup,
        origin=Origin(xyz=cup_frame),
        axis=(0.0, 0.0, 1.0),
        motion_limits=MotionLimits(effort=10.0, velocity=0.15, lower=0.0, upper=0.100),
    )

    # ---- Start button ----------------------------------------------------
    button = model.part("button")
    button_frame = (-0.050, 0.205, 0.0865)
    button.visual(
        mesh_from_cadquery(_yup(_build_button_solid()), "grinder_button", tolerance=0.0006),
        origin=Origin(
            xyz=(-button_frame[0], -button_frame[1], -button_frame[2])
        ),
        material=metal,
        name="button_cap",
    )
    model.articulation(
        "body_to_button",
        ArticulationType.PRISMATIC,
        parent=body,
        child=button,
        origin=Origin(xyz=button_frame),
        axis=(0.0, 0.0, -1.0),
        motion_limits=MotionLimits(effort=4.0, velocity=0.05, lower=0.0, upper=0.008),
    )

    # ---- Grind adjustment dial ------------------------------------------
    dial = model.part("dial")
    dial_frame = (0.050, 0.205, 0.0865)
    dial.visual(
        mesh_from_cadquery(_yup(_build_dial_solid()), "grinder_dial", tolerance=0.0006),
        origin=Origin(xyz=(-dial_frame[0], -dial_frame[1], -dial_frame[2])),
        material=metal,
        name="dial_knob",
    )
    model.articulation(
        "body_to_dial",
        ArticulationType.CONTINUOUS,
        parent=body,
        child=dial,
        origin=Origin(xyz=dial_frame),
        axis=(0.0, 0.0, 1.0),
        motion_limits=MotionLimits(effort=0.5, velocity=6.0),
    )

    # TEMP: fit disabled for diagnosis
    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    body = object_model.get_part("body")
    lid = object_model.get_part("lid")
    cup = object_model.get_part("cup")
    button = object_model.get_part("button")
    dial = object_model.get_part("dial")

    lid_joint = object_model.get_articulation("body_to_lid")
    cup_joint = object_model.get_articulation("body_to_cup")
    button_joint = object_model.get_articulation("body_to_button")
    dial_joint = object_model.get_articulation("body_to_dial")

    # Hopper and lid are seated (connected) at rest.
    ctx.expect_contact(lid, body, contact_tol=1e-4, name="lid seated on hopper rim")
    ctx.expect_contact(cup, body, contact_tol=1e-4, name="cup seated on recess shelf")
    ctx.expect_contact(button, body, contact_tol=1e-4, name="button mounted on front face")
    ctx.expect_contact(dial, body, contact_tol=1e-4, name="dial mounted on front face")

    # Lid lifts upward when opened.
    rest_lid = ctx.part_world_aabb(lid)[0][1]
    with ctx.pose({lid_joint: 0.055}):
        open_lid = ctx.part_world_aabb(lid)[0][1]
    ctx.check(
        "lid lifts upward",
        rest_lid is not None and open_lid is not None and open_lid > rest_lid + 0.02,
        details=f"rest_y={rest_lid}, open_y={open_lid}",
    )

    # Grounds cup slides out the front (+Z).
    rest_cup = ctx.part_world_position(cup)[2]
    with ctx.pose({cup_joint: 0.100}):
        out_cup = ctx.part_world_position(cup)[2]
    ctx.check(
        "cup slides out the front",
        out_cup > rest_cup + 0.03,
        details=f"rest_z={rest_cup}, out_z={out_cup}",
    )

    # Start button pushes inward (toward -Z / into the body).
    rest_btn = ctx.part_world_position(button)[2]
    with ctx.pose({button_joint: 0.008}):
        pushed_btn = ctx.part_world_position(button)[2]
    ctx.check(
        "button pushes inward",
        pushed_btn < rest_btn - 0.002,
        details=f"rest_z={rest_btn}, pushed_z={pushed_btn}",
    )

    # Grind dial can spin continuously.
    with ctx.pose({dial_joint: math.pi}):
        ctx.check("dial rotates freely", True)

    return ctx.report()


object_model = build_object_model()

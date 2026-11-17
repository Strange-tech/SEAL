from __future__ import annotations

import math

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Box,
    Cylinder,
    Origin,
    MotionLimits,
    TestContext,
    TestReport,
    WheelGeometry,
    WheelRim,
    WheelHub,
    WheelFace,
    WheelSpokes,
    WheelBore,
    TireGeometry,
    TireGroove,
    TireSidewall,
    TireTread,
    mesh_from_geometry,
)

# ---------------------------------------------------------------------------
# Object-intrinsic frame: +Y up, +Z forward (front of bike), +X lateral.
# Ground plane at y = 0.
# ---------------------------------------------------------------------------

BB = (0.0, 0.28, -0.14)          # bottom bracket
R_AXLE = (0.0, 0.34, -0.51)      # rear axle
F_AXLE = (0.0, 0.34, 0.51)       # front axle
HEAD_BOT = (0.0, 0.62, 0.48)     # fork crown / bottom of head tube
HEAD_TOP = (0.0, 0.82, 0.42)     # top of head tube
SEAT_CL = (0.0, 0.70, -0.28)     # seat cluster (top of seat tube)

WHEEL_R = 0.34                   # tire outer radius
RIM_R = 0.312
TIRE_W = 0.026
FRONT_HUB_W = 0.090
REAR_HUB_W = 0.130
FRONT_DROPOUT_X = FRONT_HUB_W / 2.0
REAR_DROPOUT_X = REAR_HUB_W / 2.0


def _norm(v):
    L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if L == 0.0:
        return (0.0, 0.0, 1.0)
    return (v[0] / L, v[1] / L, v[2] / L)


def _add(a, b, s=1.0):
    return (a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add_tube(part, a, b, r, mat, name, off=(0.0, 0.0, 0.0)):
    """Add a cylinder (round tube) between world points a and b."""
    ax = _sub(a, off)
    bx = _sub(b, off)
    d = _sub(bx, ax)
    L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
    u = _norm(d)
    pitch = math.acos(max(-1.0, min(1.0, u[2])))
    yaw = math.atan2(u[1], u[0])
    mid = ((ax[0] + bx[0]) / 2.0, (ax[1] + bx[1]) / 2.0, (ax[2] + bx[2]) / 2.0)
    part.visual(
        Cylinder(radius=r, length=L),
        origin=Origin(xyz=mid, rpy=(0.0, pitch, yaw)),
        material=mat,
        name=name,
    )


def add_box(part, size, center, mat, name, off=(0.0, 0.0, 0.0), rpy=(0.0, 0.0, 0.0)):
    c = _sub(center, off)
    part.visual(Box(size), origin=Origin(xyz=c, rpy=rpy), material=mat, name=name)


def add_cyl_x(part, radius, length, center, mat, name, off=(0.0, 0.0, 0.0)):
    c = _sub(center, off)
    part.visual(
        Cylinder(radius=radius, length=length),
        origin=Origin(xyz=c, rpy=(0.0, math.pi / 2.0, 0.0)),
        material=mat,
        name=name,
    )


def _build_wheel(part, metal, dark, rubber, hub_width, prefix):
    part.visual(
        mesh_from_geometry(
            WheelGeometry(
                RIM_R,
                TIRE_W,
                rim=WheelRim(
                    inner_radius=RIM_R - 0.017,
                    flange_height=0.008,
                    flange_thickness=0.003,
                    bead_seat_depth=0.003,
                ),
                hub=WheelHub(radius=0.020, width=hub_width, cap_style="domed"),
                face=WheelFace(dish_depth=0.004, front_inset=0.002, rear_inset=0.001),
                spokes=WheelSpokes(style="straight", count=16, thickness=0.0016, window_radius=0.005),
                bore=WheelBore(style="round", diameter=0.008),
            ),
            f"{prefix}_wheel",
        ),
        material=metal,
        name=f"{prefix}_rim",
    )
    part.visual(
        mesh_from_geometry(
            TireGeometry(
                WHEEL_R,
                TIRE_W,
                inner_radius=RIM_R,
                tread=TireTread(style="circumferential", depth=0.003, count=3),
                grooves=(TireGroove(center_offset=0.0, width=0.004, depth=0.0015),),
                sidewall=TireSidewall(style="rounded", bulge=0.06),
            ),
            f"{prefix}_tire",
        ),
        material=rubber,
        name=f"{prefix}_tire",
    )


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="bicycle")

    paint = model.material("frame_paint", rgba=(0.46, 0.06, 0.09, 1.0))
    steel = model.material("wheel_steel", rgba=(0.72, 0.74, 0.77, 1.0))
    dark = model.material("dark_steel", rgba=(0.22, 0.23, 0.25, 1.0))
    rubber = model.material("rubber_black", rgba=(0.045, 0.045, 0.05, 1.0))
    saddle_mat = model.material("saddle_black", rgba=(0.07, 0.07, 0.08, 1.0))

    steer_axis = _norm(_sub(HEAD_TOP, HEAD_BOT))
    seat_axis = _norm(_sub(SEAT_CL, BB))

    # ---------------- Frame (root) ----------------
    frame = model.part("frame")

    # main triangle
    add_tube(frame, HEAD_BOT, BB, 0.020, paint, "down_tube")
    add_tube(frame, HEAD_TOP, _add(SEAT_CL, (0, -0.02, 0.01)), 0.016, paint, "top_tube")
    add_tube(frame, BB, SEAT_CL, 0.018, paint, "seat_tube")
    add_tube(frame, HEAD_BOT, HEAD_TOP, 0.021, paint, "head_tube")
    # BB shell
    add_cyl_x(frame, 0.026, 0.070, BB, paint, "bb_shell")

    # chain stays and seat stays (two per side)
    for s in (-1.0, 1.0):
        add_tube(
            frame,
            (s * 0.018, BB[1], BB[2] + 0.01),
            (s * REAR_DROPOUT_X, R_AXLE[1], R_AXLE[2]),
            0.012,
            paint,
            f"chain_stay_{'p' if s > 0 else 'n'}",
        )
        add_tube(
            frame,
            (s * 0.018, SEAT_CL[1] - 0.03, SEAT_CL[2]),
            (s * REAR_DROPOUT_X, R_AXLE[1], R_AXLE[2]),
            0.010,
            paint,
            f"seat_stay_{'p' if s > 0 else 'n'}",
        )
        # rear dropout plate
        add_box(
            frame,
            (0.012, 0.05, 0.035),
            (s * REAR_DROPOUT_X, R_AXLE[1], R_AXLE[2]),
            dark,
            f"rear_dropout_{'p' if s > 0 else 'n'}",
        )

    # rear brake caliper (mounts on seat stay bridge)
    add_box(frame, (0.05, 0.05, 0.018), (0.0, 0.63, -0.49), dark, "rear_brake_caliper")
    add_box(frame, (0.02, 0.05, 0.05), (0.0, 0.60, -0.46), dark, "rear_brake_arm")

    # chain: two thin runs between chainring and rear sprocket
    add_tube(frame, (0.062, 0.378, -0.14), (0.066, 0.385, -0.51), 0.005, dark, "chain_top")
    add_tube(frame, (0.062, 0.182, -0.14), (0.066, 0.295, -0.51), 0.005, dark, "chain_bottom")

    # ---------------- Fork ----------------
    fork = model.part("fork")
    fo = HEAD_BOT  # fork part origin at the crown / steering pivot
    # steerer tube along the steering axis, from below the crown to above the head tube
    steer_low = _add(HEAD_BOT, steer_axis, -0.03)
    steer_high = _add(HEAD_BOT, steer_axis, 0.26)
    add_tube(fork, steer_low, steer_high, 0.014, steel, "steerer", off=fo)
    # fork crown
    add_box(fork, (0.09, 0.032, 0.05), (0.0, 0.605, 0.485), paint, "fork_crown", off=fo)
    # blades: crown -> dropout with a slight forward bend
    for s in (-1.0, 1.0):
        add_tube(
            fork,
            (s * 0.030, 0.595, 0.487),
            (s * FRONT_DROPOUT_X, 0.46, 0.505),
            0.011,
            paint,
            f"fork_blade_up_{'p' if s > 0 else 'n'}",
            off=fo,
        )
        add_tube(
            fork,
            (s * FRONT_DROPOUT_X, 0.46, 0.505),
            (s * FRONT_DROPOUT_X, F_AXLE[1], F_AXLE[2]),
            0.010,
            paint,
            f"fork_blade_low_{'p' if s > 0 else 'n'}",
            off=fo,
        )
        add_box(
            fork,
            (0.010, 0.05, 0.035),
            (s * FRONT_DROPOUT_X, F_AXLE[1], F_AXLE[2]),
            dark,
            f"front_dropout_{'p' if s > 0 else 'n'}",
            off=fo,
        )
    # front brake caliper on the crown
    add_box(fork, (0.05, 0.045, 0.018), (0.0, 0.635, 0.50), dark, "front_brake_caliper", off=fo)

    # ---------------- Handlebar (fixed to fork) ----------------
    handlebar = model.part("handlebar")
    hb_top = steer_high  # steerer top
    ho = hb_top
    bar_center = (0.0, 0.945, 0.44)
    add_tube(handlebar, hb_top, bar_center, 0.012, dark, "stem", off=ho)
    # clamp
    add_box(handlebar, (0.05, 0.04, 0.04), bar_center, dark, "stem_clamp", off=ho)
    # main bar across X
    add_tube(handlebar, (-0.21, 0.945, 0.44), (0.21, 0.945, 0.44), 0.011, dark, "handlebar_bar", off=ho)
    # grips
    add_cyl_x(handlebar, 0.015, 0.09, (0.185, 0.945, 0.44), rubber, "grip_p", off=ho)
    add_cyl_x(handlebar, 0.015, 0.09, (-0.185, 0.945, 0.44), rubber, "grip_n", off=ho)
    # brake levers
    add_box(handlebar, (0.018, 0.02, 0.06), (0.155, 0.935, 0.46), dark, "lever_p", off=ho)
    add_box(handlebar, (0.018, 0.02, 0.06), (-0.155, 0.935, 0.46), dark, "lever_n", off=ho)

    # ---------------- Front wheel ----------------
    front_wheel = model.part("front_wheel")
    _build_wheel(front_wheel, steel, dark, rubber, FRONT_HUB_W, "front")

    # ---------------- Rear wheel ----------------
    rear_wheel = model.part("rear_wheel")
    _build_wheel(rear_wheel, steel, dark, rubber, REAR_HUB_W, "rear")
    # rear sprocket (drive side, +X)
    add_cyl_x(rear_wheel, 0.045, 0.006, (REAR_HUB_W / 2.0, 0.0, 0.0), dark, "rear_sprocket")

    # ---------------- Crankset ----------------
    crank = model.part("crankset")
    co = BB
    # spindle through the BB
    add_cyl_x(crank, 0.012, 0.16, BB, steel, "bb_spindle", off=co)
    # chainring (drive side, +X)
    add_cyl_x(crank, 0.098, 0.004, (BB[0] + 0.062, BB[1], BB[2]), steel, "chainring", off=co)
    add_cyl_x(crank, 0.030, 0.006, (BB[0] + 0.062, BB[1], BB[2]), dark, "chainring_spider", off=co)
    # crank arms: one up (non-drive, -X), one down (drive, +X)
    add_box(crank, (0.016, 0.17, 0.032), (BB[0] - 0.075, BB[1] + 0.085, BB[2]), steel, "crank_arm_n", off=co)
    add_box(crank, (0.016, 0.17, 0.032), (BB[0] + 0.075, BB[1] - 0.085, BB[2]), steel, "crank_arm_p", off=co)

    # ---------------- Pedals (two, revolute on crank spindle) ----------------
    def build_pedal(part, px):
        # part frame sits at the crank-arm end; spindle along X
        part.visual(
            Cylinder(radius=0.005, length=0.11),
            origin=Origin(xyz=(0, 0, 0), rpy=(0, math.pi / 2.0, 0)),
            material=steel,
            name="pedal_spindle",
        )
        part.visual(Box((0.09, 0.018, 0.065)), origin=Origin(xyz=(0, 0, 0)), material=dark, name="pedal_body")
        part.visual(Box((0.05, 0.01, 0.02)), origin=Origin(xyz=(0, 0.014, 0)), material=rubber, name="pedal_grip")

    pedal_0 = model.part("pedal_0")
    build_pedal(pedal_0, BB[0] + 0.075)
    pedal_1 = model.part("pedal_1")
    build_pedal(pedal_1, BB[0] - 0.075)

    # ---------------- Seatpost ----------------
    seatpost = model.part("seatpost")
    so = SEAT_CL
    sp_bot = _add(SEAT_CL, seat_axis, -0.08)
    sp_top = _add(SEAT_CL, seat_axis, 0.25)
    add_tube(seatpost, sp_bot, sp_top, 0.0125, steel, "seatpost_tube", off=so)

    # ---------------- Saddle (fixed to seatpost) ----------------
    saddle = model.part("saddle")
    # part frame at the seatpost top; geometry sits above
    saddle.visual(Box((0.15, 0.028, 0.12)), origin=Origin(xyz=(0.0, 0.020, -0.075)), material=saddle_mat, name="saddle_rear")
    saddle.visual(Box((0.115, 0.028, 0.10)), origin=Origin(xyz=(0.0, 0.022, 0.010)), material=saddle_mat, name="saddle_mid")
    saddle.visual(Box((0.055, 0.026, 0.12)), origin=Origin(xyz=(0.0, 0.024, 0.115)), material=saddle_mat, name="saddle_nose")
    saddle.visual(Box((0.05, 0.03, 0.06)), origin=Origin(xyz=(0.0, 0.0, -0.02)), material=dark, name="saddle_clamp")

    # =====================================================================
    # Articulations
    # =====================================================================
    # Steering hinge: frame -> fork, about the steering axis
    model.articulation(
        "steering",
        ArticulationType.REVOLUTE,
        parent=frame,
        child=fork,
        origin=Origin(xyz=HEAD_BOT),
        axis=steer_axis,
        motion_limits=MotionLimits(effort=15.0, velocity=3.0, lower=-0.55, upper=0.55),
    )
    # Handlebar fixed to fork at the steerer top
    model.articulation(
        "fork_to_handlebar",
        ArticulationType.FIXED,
        parent=fork,
        child=handlebar,
        origin=Origin(xyz=_sub(hb_top, HEAD_BOT)),
    )
    # Front wheel spins about its axle, carried by the fork
    model.articulation(
        "fork_to_front_wheel",
        ArticulationType.CONTINUOUS,
        parent=fork,
        child=front_wheel,
        origin=Origin(xyz=_sub(F_AXLE, HEAD_BOT)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=10.0, velocity=30.0),
    )
    # Rear wheel spins about its axle, carried by the frame
    model.articulation(
        "frame_to_rear_wheel",
        ArticulationType.CONTINUOUS,
        parent=frame,
        child=rear_wheel,
        origin=Origin(xyz=R_AXLE),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=10.0, velocity=30.0),
    )
    # Crankset rotates about the bottom bracket
    model.articulation(
        "frame_to_crankset",
        ArticulationType.REVOLUTE,
        parent=frame,
        child=crank,
        origin=Origin(xyz=BB),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=40.0, velocity=10.0, lower=-6.283, upper=6.283),
    )
    # Pedals spin on their spindles
    model.articulation(
        "crank_to_pedal_0",
        ArticulationType.CONTINUOUS,
        parent=crank,
        child=pedal_0,
        origin=Origin(xyz=(0.075, -0.17, 0.0)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=5.0, velocity=20.0),
    )
    model.articulation(
        "crank_to_pedal_1",
        ArticulationType.CONTINUOUS,
        parent=crank,
        child=pedal_1,
        origin=Origin(xyz=(-0.075, 0.17, 0.0)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=5.0, velocity=20.0),
    )
    # Seatpost slides in the seat tube
    model.articulation(
        "frame_to_seatpost",
        ArticulationType.PRISMATIC,
        parent=frame,
        child=seatpost,
        origin=Origin(xyz=SEAT_CL),
        axis=seat_axis,
        motion_limits=MotionLimits(effort=30.0, velocity=0.10, lower=-0.04, upper=0.10),
    )
    # Saddle fixed on the seatpost top
    model.articulation(
        "seatpost_to_saddle",
        ArticulationType.FIXED,
        parent=seatpost,
        child=saddle,
        origin=Origin(xyz=_add((0.0, 0.0, 0.0), seat_axis, 0.25)),
    )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    frame = object_model.get_part("frame")
    fork = object_model.get_part("fork")
    front_wheel = object_model.get_part("front_wheel")
    rear_wheel = object_model.get_part("rear_wheel")
    crank = object_model.get_part("crankset")
    pedal_0 = object_model.get_part("pedal_0")
    pedal_1 = object_model.get_part("pedal_1")
    seatpost = object_model.get_part("seatpost")
    saddle = object_model.get_part("saddle")

    steering = object_model.get_articulation("steering")
    front_spin = object_model.get_articulation("fork_to_front_wheel")
    crank_joint = object_model.get_articulation("frame_to_crankset")
    seat_joint = object_model.get_articulation("frame_to_seatpost")

    # Bearing-mounted / sliding subassemblies held with running clearance.
    ctx.allow_isolated_part(
        crank, reason="Crankset is carried in the bottom-bracket bearing with running clearance."
    )
    ctx.allow_isolated_part(pedal_0, reason="Pedal rides on the crank spindle bearing.")
    ctx.allow_isolated_part(pedal_1, reason="Pedal rides on the crank spindle bearing.")
    ctx.allow_isolated_part(
        seatpost, reason="Seatpost slides inside the seat tube with running clearance."
    )
    ctx.allow_isolated_part(saddle, reason="Saddle is bolted to the (bearing-mounted) seatpost.")

    # ---- Wheels read as real road wheels (~0.68 m diameter) ----
    fa = ctx.part_world_aabb(front_wheel)
    ra = ctx.part_world_aabb(rear_wheel)
    if fa is not None:
        f_min, f_max = fa
        fy = f_max[1] - f_min[1]
        fz = f_max[2] - f_min[2]
        ctx.check("front_wheel_diameter", 0.66 <= max(fy, fz) <= 0.70, f"diam={max(fy, fz):.3f}")
    if ra is not None:
        r_min, r_max = ra
        ry = r_max[1] - r_min[1]
        rz = r_max[2] - r_min[2]
        ctx.check("rear_wheel_diameter", 0.66 <= max(ry, rz) <= 0.70, f"diam={max(ry, rz):.3f}")

    # ---- Wheels are carried by fork / frame (dropout contact) ----
    ctx.expect_contact(front_wheel, fork, contact_tol=0.003, name="front wheel seated in fork")
    ctx.expect_contact(rear_wheel, frame, contact_tol=0.003, name="rear wheel seated in frame")

    # ---- Steering turns the front wheel laterally ----
    rest = ctx.part_world_position(front_wheel)
    with ctx.pose({steering: 0.45}):
        turned = ctx.part_world_position(front_wheel)
    ctx.check(
        "steering_turns_front_wheel",
        rest is not None and turned is not None and abs(turned[0] - rest[0]) > 0.05,
        f"rest={rest}, turned={turned}",
    )

    # ---- Seatpost slide raises the saddle ----
    s_rest = ctx.part_world_position(saddle)
    with ctx.pose({seat_joint: 0.10}):
        s_up = ctx.part_world_position(saddle)
    ctx.check(
        "seatpost_raises_saddle",
        s_rest is not None and s_up is not None and s_up[1] > s_rest[1] + 0.03,
        f"rest={s_rest}, up={s_up}",
    )

    # ---- Crankset rotation moves a pedal ----
    p_rest = ctx.part_world_position(pedal_0)
    with ctx.pose({crank_joint: 0.6}):
        p_moved = ctx.part_world_position(pedal_0)
    ctx.check(
        "crankset_rotates_pedal",
        p_rest is not None and p_moved is not None
        and (abs(p_moved[1] - p_rest[1]) + abs(p_moved[2] - p_rest[2])) > 0.03,
        f"rest={p_rest}, moved={p_moved}",
    )

    return ctx.report()


object_model = build_object_model()

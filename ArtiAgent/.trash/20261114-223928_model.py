from __future__ import annotations

import math

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Box,
    Cylinder,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    TireGeometry,
    TireSidewall,
    TireTread,
    WheelBore,
    WheelFace,
    WheelGeometry,
    WheelHub,
    WheelRim,
    WheelSpokes,
    mesh_from_geometry,
    tube_from_spline_points,
)

# ---------------------------------------------------------------------------
# Author the bicycle at natural size in y-up / +z-forward, then shift the whole
# assembly so its box centre lands on the layout target.  Only ROOT-part
# visuals and depth-1 articulation origins carry the offset; child parts are
# authored in their parent-local frames.
# ---------------------------------------------------------------------------
OX, OY, OZ = 4.8, 0.0, 2.495

# ---- key design points (metres, y-up / +z forward) -------------------------
R_TIRE = 0.34
TIRE_W = 0.038

FRONT_AXLE = (0.0, 0.34, 0.53)
REAR_AXLE = (0.0, 0.34, -0.52)
BB = (0.0, 0.27, -0.09)           # bottom bracket centre
CLUSTER = (0.0, 0.76, -0.25)      # seat tube top / seat cluster
HEAD_BOT = (0.0, 0.71, 0.42)      # fork crown / head tube bottom (above tyre)
HEAD_TOP = (0.0, 0.86, 0.36)
STEER_TOP = (0.0, 0.90, 0.33)

P_STEER = HEAD_BOT
DS = (HEAD_TOP[0] - HEAD_BOT[0], HEAD_TOP[1] - HEAD_BOT[1], HEAD_TOP[2] - HEAD_BOT[2])
DS_SEAT = (CLUSTER[0] - BB[0], CLUSTER[1] - BB[1], CLUSTER[2] - BB[2])


def _norm(v):
    l = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    return (v[0] / l, v[1] / l, v[2] / l)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


DS_N = _norm(DS)
DS_SEAT_N = _norm(DS_SEAT)


def _mesh(name, geom):
    return mesh_from_geometry(geom, name)


def _tube(name, points, radius, offset=False, closed=False, sps=10, rs=14):
    if offset:
        points = [(p[0] + OX, p[1] + OY, p[2] + OZ) for p in points]
    return _mesh(
        name,
        tube_from_spline_points(
            points,
            radius=radius,
            samples_per_segment=sps,
            radial_segments=rs,
            closed_spline=closed,
            cap_ends=not closed,
        ),
    )


def _cyl_x(radius, length):
    return Cylinder(radius=radius, length=length)


def _add_wheel_visuals(part, prefix, steel, rubber, axle_len, with_cog=False):
    part.visual(
        _mesh(
            prefix + "_rim",
            WheelGeometry(
                0.300,
                0.040,
                rim=WheelRim(inner_radius=0.240, flange_height=0.008, flange_thickness=0.003),
                hub=WheelHub(radius=0.028, width=0.070, cap_style="domed"),
                face=WheelFace(dish_depth=0.004),
                spokes=WheelSpokes(style="straight", count=24, thickness=0.002, window_radius=0.004),
                bore=WheelBore(style="round", diameter=0.012),
            ),
        ),
        material=steel,
        name="rim",
    )
    part.visual(
        _mesh(
            prefix + "_tire",
            TireGeometry(
                R_TIRE,
                TIRE_W,
                inner_radius=0.300,
                tread=TireTread(style="circumferential", depth=0.003, count=6),
                sidewall=TireSidewall(style="rounded", bulge=0.05),
            ),
        ),
        material=rubber,
        name="tire",
    )
    # through-axle stub reaching the dropouts
    part.visual(_cyl_x(0.006, axle_len), origin=Origin(rpy=(0.0, math.pi / 2.0, 0.0)), material=steel, name="axle")
    if with_cog:
        part.visual(_cyl_x(0.020, 0.070), origin=Origin(xyz=(0.060, 0.0, 0.0), rpy=(0.0, math.pi / 2.0, 0.0)), material=steel, name="freewheel")
        part.visual(_cyl_x(0.045, 0.004), origin=Origin(xyz=(0.075, 0.0, 0.0), rpy=(0.0, math.pi / 2.0, 0.0)), material=steel, name="cog")


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="bicycle")

    frame_paint = model.material("frame_paint", rgba=(0.09, 0.20, 0.42, 1.0))
    steel = model.material("steel", rgba=(0.72, 0.74, 0.78, 1.0))
    rubber = model.material("rubber", rgba=(0.05, 0.05, 0.06, 1.0))
    saddle_vinyl = model.material("saddle_vinyl", rgba=(0.10, 0.10, 0.11, 1.0))
    chain_steel = model.material("chain_steel", rgba=(0.22, 0.23, 0.25, 1.0))

    # =====================================================================
    # FRAME (root) -- authored in world coords + global offset
    # =====================================================================
    frame = model.part("frame")
    FR = True

    frame.visual(_tube("frame_down_tube", [BB, HEAD_BOT], 0.017, offset=FR), material=frame_paint, name="down_tube")
    frame.visual(_tube("frame_seat_tube", [BB, CLUSTER], 0.016, offset=FR), material=frame_paint, name="seat_tube")
    frame.visual(_tube("frame_top_tube", [(0.0, 0.74, -0.24), (0.0, 0.80, 0.375)], 0.016, offset=FR), material=frame_paint, name="top_tube")
    frame.visual(_tube("frame_head_tube", [HEAD_BOT, HEAD_TOP], 0.021, offset=FR), material=frame_paint, name="head_tube")
    # stays: splayed outboard of the wheel
    frame.visual(_tube("frame_chainstay_l", [(0.025, 0.27, -0.10), (0.055, 0.34, -0.52)], 0.010, offset=FR), material=frame_paint, name="chainstay_l")
    frame.visual(_tube("frame_chainstay_r", [(-0.025, 0.27, -0.10), (-0.055, 0.34, -0.52)], 0.010, offset=FR), material=frame_paint, name="chainstay_r")
    frame.visual(_tube("frame_seatstay_l", [(0.030, 0.74, -0.25), (0.055, 0.34, -0.52)], 0.009, offset=FR), material=frame_paint, name="seatstay_l")
    frame.visual(_tube("frame_seatstay_r", [(-0.030, 0.74, -0.25), (-0.055, 0.34, -0.52)], 0.009, offset=FR), material=frame_paint, name="seatstay_r")
    # seat cluster lug
    frame.visual(Box((0.070, 0.030, 0.030)), origin=Origin(xyz=(0.0 + OX, 0.745 + OY, -0.25 + OZ)), material=frame_paint, name="seat_cluster")
    # bottom bracket shell
    frame.visual(_cyl_x(0.024, 0.090), origin=Origin(xyz=(BB[0] + OX, BB[1] + OY, BB[2] + OZ), rpy=(0.0, math.pi / 2.0, 0.0)), material=frame_paint, name="bb_shell")
    # rear dropouts
    frame.visual(Box((0.012, 0.055, 0.055)), origin=Origin(xyz=(0.055 + OX, 0.34 + OY, -0.52 + OZ)), material=frame_paint, name="rear_dropout_l")
    frame.visual(Box((0.012, 0.055, 0.055)), origin=Origin(xyz=(-0.055 + OX, 0.34 + OY, -0.52 + OZ)), material=frame_paint, name="rear_dropout_r")

    # =====================================================================
    # FORK (child of frame, steers about head-tube axis) -- local frame at P_STEER
    # =====================================================================
    fork = model.part("fork")

    def fp(p):
        return _sub(p, P_STEER)

    fork.visual(_tube("fork_steerer", [fp((0.0, 0.685, 0.428)), fp(STEER_TOP)], 0.014), material=steel, name="steerer")
    fork.visual(Box((0.100, 0.034, 0.05)), origin=Origin(xyz=fp((0.0, 0.70, 0.42))), material=frame_paint, name="crown")
    blade_l = [fp(p) for p in [
        (0.044, 0.705, 0.420),
        (0.050, 0.620, 0.440),
        (0.052, 0.500, 0.485),
        (0.050, 0.400, 0.518),
        (0.050, 0.340, 0.530),
    ]]
    fork.visual(_tube("fork_blade_l", blade_l, 0.012, sps=8), material=frame_paint, name="blade_l")
    blade_r = [fp(p) for p in [
        (-0.044, 0.705, 0.420),
        (-0.050, 0.620, 0.440),
        (-0.052, 0.500, 0.485),
        (-0.050, 0.400, 0.518),
        (-0.050, 0.340, 0.530),
    ]]
    fork.visual(_tube("fork_blade_r", blade_r, 0.012, sps=8), material=frame_paint, name="blade_r")
    fork.visual(Box((0.012, 0.05, 0.05)), origin=Origin(xyz=fp((0.056, 0.34, 0.53))), material=frame_paint, name="front_dropout_l")
    fork.visual(Box((0.012, 0.05, 0.05)), origin=Origin(xyz=fp((-0.056, 0.34, 0.53))), material=frame_paint, name="front_dropout_r")

    # =====================================================================
    # HANDLEBAR (child of fork, fixed) -- local frame at STEER_TOP
    # =====================================================================
    handlebar = model.part("handlebar")

    def hp(p):
        return _sub(p, STEER_TOP)

    handlebar.visual(_tube("hb_stem", [(0.0, 0.0, 0.0), hp((0.0, 0.955, 0.39))], 0.016), material=steel, name="stem")
    bar_pts = [hp(p) for p in [
        (-0.26, 0.950, 0.375),
        (-0.18, 0.953, 0.390),
        (-0.06, 0.955, 0.400),
        (0.06, 0.955, 0.400),
        (0.18, 0.953, 0.390),
        (0.26, 0.950, 0.375),
    ]]
    handlebar.visual(_tube("hb_bar", bar_pts, 0.012, sps=8, rs=16), material=steel, name="bar")
    handlebar.visual(_cyl_x(0.015, 0.075), origin=Origin(xyz=hp((-0.225, 0.951, 0.378)), rpy=(0.0, math.pi / 2.0, 0.0)), material=rubber, name="grip_l")
    handlebar.visual(_cyl_x(0.015, 0.075), origin=Origin(xyz=hp((0.225, 0.951, 0.378)), rpy=(0.0, math.pi / 2.0, 0.0)), material=rubber, name="grip_r")

    # =====================================================================
    # WHEELS
    # =====================================================================
    front_wheel = model.part("front_wheel")
    _add_wheel_visuals(front_wheel, "front", steel, rubber, axle_len=0.100, with_cog=False)

    rear_wheel = model.part("rear_wheel")
    _add_wheel_visuals(rear_wheel, "rear", steel, rubber, axle_len=0.110, with_cog=True)

    # =====================================================================
    # SEATPOST (child of frame, prismatic) + SADDLE (child of seatpost)
    # =====================================================================
    seatpost = model.part("seatpost")
    sp_bottom = tuple(-0.07 * c for c in DS_SEAT_N)
    sp_top = tuple(0.18 * c for c in DS_SEAT_N)
    seatpost.visual(_tube("seatpost_tube", [sp_bottom, sp_top], 0.0135, sps=6), material=steel, name="post")

    saddle = model.part("saddle")
    saddle.visual(Box((0.032, 0.032, 0.060)), origin=Origin(xyz=(0.0, 0.016, 0.0)), material=saddle_vinyl, name="clamp")
    saddle.visual(_tube("saddle_rail_l", [(0.026, 0.012, -0.05), (0.050, 0.040, 0.08)], 0.005, sps=6, rs=10), material=steel, name="rail_l")
    saddle.visual(_tube("saddle_rail_r", [(-0.026, 0.012, -0.05), (-0.050, 0.040, 0.08)], 0.005, sps=6, rs=10), material=steel, name="rail_r")
    saddle.visual(Box((0.135, 0.040, 0.150)), origin=Origin(xyz=(0.0, 0.052, -0.03)), material=saddle_vinyl, name="seat_body")
    saddle.visual(Box((0.070, 0.032, 0.130)), origin=Origin(xyz=(0.0, 0.046, 0.10)), material=saddle_vinyl, name="seat_nose")

    # =====================================================================
    # CRANKSET (child of frame, continuous about BB) -- local frame at BB
    # =====================================================================
    crankset = model.part("crankset")
    crankset.visual(_cyl_x(0.013, 0.160), origin=Origin(), material=steel, name="spindle")
    crankset.visual(Box((0.013, 0.030, 0.170)), origin=Origin(xyz=(-0.0515, 0.0, 0.085)), material=steel, name="crank_arm_l")
    crankset.visual(Box((0.013, 0.030, 0.170)), origin=Origin(xyz=(0.0515, 0.0, -0.085)), material=steel, name="crank_arm_r")
    crankset.visual(_cyl_x(0.100, 0.006), origin=Origin(xyz=(0.075, 0.0, 0.0), rpy=(0.0, math.pi / 2.0, 0.0)), material=steel, name="chainring")

    pedal_left = model.part("pedal_left")
    pedal_left.visual(_cyl_x(0.006, 0.055), origin=Origin(xyz=(-0.0275, 0.0, 0.0), rpy=(0.0, math.pi / 2.0, 0.0)), material=steel, name="spindle")
    pedal_left.visual(Box((0.060, 0.020, 0.090)), origin=Origin(xyz=(-0.060, 0.0, 0.0)), material=rubber, name="platform")

    pedal_right = model.part("pedal_right")
    pedal_right.visual(_cyl_x(0.006, 0.055), origin=Origin(xyz=(0.0275, 0.0, 0.0), rpy=(0.0, math.pi / 2.0, 0.0)), material=steel, name="spindle")
    pedal_right.visual(Box((0.060, 0.020, 0.090)), origin=Origin(xyz=(0.060, 0.0, 0.0)), material=rubber, name="platform")

    # =====================================================================
    # CHAIN (fixed accessory loop around chainring + rear cog) -- local at BB
    # =====================================================================
    chain = model.part("chain")
    chain_pts = [
        (0.075, 0.106, 0.0),
        (0.075, 0.121, -0.43),
        (0.075, 0.019, -0.43),
        (0.075, -0.106, 0.0),
    ]
    chain.visual(_tube("chain_loop", chain_pts, 0.006, closed=True, sps=10, rs=8), material=chain_steel, name="loop")

    # =====================================================================
    # ARTICULATIONS
    # =====================================================================
    model.articulation(
        "frame_to_fork",
        ArticulationType.REVOLUTE,
        parent=frame,
        child=fork,
        origin=Origin(xyz=(P_STEER[0] + OX, P_STEER[1] + OY, P_STEER[2] + OZ)),
        axis=DS_N,
        motion_limits=MotionLimits(effort=10.0, velocity=3.0, lower=-0.5, upper=0.5),
    )
    model.articulation(
        "fork_to_front_wheel",
        ArticulationType.CONTINUOUS,
        parent=fork,
        child=front_wheel,
        origin=Origin(xyz=fp(FRONT_AXLE)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=6.0, velocity=30.0),
    )
    model.articulation(
        "fork_to_handlebar",
        ArticulationType.FIXED,
        parent=fork,
        child=handlebar,
        origin=Origin(xyz=fp(STEER_TOP)),
    )
    model.articulation(
        "frame_to_rear_wheel",
        ArticulationType.CONTINUOUS,
        parent=frame,
        child=rear_wheel,
        origin=Origin(xyz=(REAR_AXLE[0] + OX, REAR_AXLE[1] + OY, REAR_AXLE[2] + OZ)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=6.0, velocity=30.0),
    )
    model.articulation(
        "frame_to_seatpost",
        ArticulationType.PRISMATIC,
        parent=frame,
        child=seatpost,
        origin=Origin(xyz=(CLUSTER[0] + OX, CLUSTER[1] + OY, CLUSTER[2] + OZ)),
        axis=DS_SEAT_N,
        motion_limits=MotionLimits(effort=60.0, velocity=0.10, lower=0.0, upper=0.09),
    )
    model.articulation(
        "seatpost_to_saddle",
        ArticulationType.FIXED,
        parent=seatpost,
        child=saddle,
        origin=Origin(xyz=sp_top),
    )
    model.articulation(
        "frame_to_crankset",
        ArticulationType.CONTINUOUS,
        parent=frame,
        child=crankset,
        origin=Origin(xyz=(BB[0] + OX, BB[1] + OY, BB[2] + OZ)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=15.0, velocity=20.0),
    )
    model.articulation(
        "crankset_to_pedal_left",
        ArticulationType.CONTINUOUS,
        parent=crankset,
        child=pedal_left,
        origin=Origin(xyz=(-0.058, 0.0, 0.17)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=3.0, velocity=20.0),
    )
    model.articulation(
        "crankset_to_pedal_right",
        ArticulationType.CONTINUOUS,
        parent=crankset,
        child=pedal_right,
        origin=Origin(xyz=(0.058, 0.0, -0.17)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=3.0, velocity=20.0),
    )
    model.articulation(
        "frame_to_chain",
        ArticulationType.FIXED,
        parent=frame,
        child=chain,
        origin=Origin(xyz=(BB[0] + OX, BB[1] + OY, BB[2] + OZ)),
    )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    frame = object_model.get_part("frame")
    fork = object_model.get_part("fork")
    handlebar = object_model.get_part("handlebar")
    front_wheel = object_model.get_part("front_wheel")
    rear_wheel = object_model.get_part("rear_wheel")
    seatpost = object_model.get_part("seatpost")
    saddle = object_model.get_part("saddle")
    crankset = object_model.get_part("crankset")
    chain = object_model.get_part("chain")

    # ---- intentional nested / wrapped fits --------------------------------
    ctx.allow_overlap(fork, frame, reason="fork steerer runs inside the frame head tube on the steering axis")
    ctx.allow_overlap(seatpost, frame, reason="seatpost is inserted into the seat tube bore")
    ctx.allow_overlap(crankset, frame, reason="bottom-bracket spindle passes through the BB shell")
    ctx.allow_overlap(chain, crankset, reason="chain wraps around the chainring")
    ctx.allow_overlap(chain, rear_wheel, reason="chain wraps around the rear cog")

    # ---- support / connectivity proofs ------------------------------------
    ctx.expect_contact(fork, frame, name="fork supported at head tube")
    ctx.expect_contact(seatpost, frame, name="seatpost inserted in seat tube")
    ctx.expect_contact(crankset, frame, name="crankset mounted at bottom bracket")
    ctx.expect_contact(front_wheel, fork, name="front wheel mounted in fork dropouts")
    ctx.expect_contact(rear_wheel, frame, name="rear wheel mounted in rear dropouts")
    ctx.expect_contact(handlebar, fork, name="handlebar clamped to steerer")
    ctx.expect_contact(saddle, seatpost, name="saddle mounted on seatpost")
    ctx.expect_contact(chain, crankset, name="chain engaged on chainring")

    # ---- steering works ---------------------------------------------------
    rest = ctx.part_world_position(front_wheel)
    with ctx.pose({"frame_to_fork": 0.4}):
        steered = ctx.part_world_position(front_wheel)
    ctx.check(
        "steering turns front wheel",
        rest is not None and steered is not None and abs(steered[0] - rest[0]) > 0.02,
        details=f"rest={rest}, steered={steered}",
    )

    # ---- seatpost raises the saddle --------------------------------------
    with ctx.pose({"frame_to_seatpost": 0.0}):
        lo = ctx.part_world_position(saddle)
    with ctx.pose({"frame_to_seatpost": 0.08}):
        hi = ctx.part_world_position(saddle)
    ctx.check(
        "seatpost lifts saddle",
        lo is not None and hi is not None and hi[1] - lo[1] > 0.05,
        details=f"lo={lo}, hi={hi}",
    )

    # ---- overall proportions ---------------------------------------------
    aabb = ctx.part_world_aabb(front_wheel)
    if aabb is not None:
        mins, maxs = aabb
        dia = max(maxs[1] - mins[1], maxs[2] - mins[2])
        ctx.check("front wheel diameter", 0.66 <= dia <= 0.70, f"dia={dia}")

    return ctx.report()


object_model = build_object_model()

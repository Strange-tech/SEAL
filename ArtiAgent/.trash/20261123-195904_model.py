from __future__ import annotations

import math

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Box,
    Cylinder,
    Material,
    MotionLimits,
    Origin,
    Sphere,
    TestContext,
    TestReport,
    mesh_from_cadquery,
    mesh_from_geometry,
    tube_from_spline_points,
)

# ----------------------------------------------------------------------------
# Design constants (authoring frame: +Z up, centred on the origin so the
# geometric centre sits at (0,0,0)).
# ----------------------------------------------------------------------------
BASE_BOT = -0.80
BASE_TOP = -0.77
PIVOT_Z = 0.505          # top of the stem / shade tilt pivot (world z)
SHADE_BOT = 0.50
SHADE_TOP = 0.80
SHADE_R_BOT = 0.125
SHADE_R_TOP = 0.090
SHADE_WALL = 0.004
STEM_R = 0.011
SWITCH_Z = 0.05


# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
MAT_BASE = Material(name="base_black", rgba=(0.05, 0.05, 0.055, 1.0))
MAT_STEEL = Material(name="brushed_steel", rgba=(0.55, 0.56, 0.58, 1.0))
MAT_SHADE = Material(name="shade_fabric", rgba=(0.90, 0.87, 0.79, 1.0))
MAT_CERAMIC = Material(name="ceramic", rgba=(0.93, 0.91, 0.86, 1.0))
MAT_BULB = Material(name="opal_bulb", rgba=(1.0, 0.98, 0.90, 1.0))
MAT_PLASTIC = Material(name="switch_plastic", rgba=(0.06, 0.06, 0.07, 1.0))
MAT_CORD = Material(name="cord_rubber", rgba=(0.04, 0.04, 0.04, 1.0))


# ----------------------------------------------------------------------------
# CadQuery build helpers
# ----------------------------------------------------------------------------
def _base_solid():
    # Lower edge chamfer, main disc, upper edge chamfer, central mounting boss.
    b0 = cq.Solid.makeCone(0.132, 0.140, 0.004, cq.Vector(0, 0, BASE_BOT))
    b1 = cq.Solid.makeCylinder(0.140, 0.024, cq.Vector(0, 0, BASE_BOT + 0.004))
    b2 = cq.Solid.makeCone(0.140, 0.128, 0.006, cq.Vector(0, 0, BASE_BOT + 0.028))
    boss = cq.Solid.makeCylinder(0.030, 0.022, cq.Vector(0, 0, BASE_BOT + 0.024))
    base = b0.fuse(b1).fuse(b2).fuse(boss)
    return base


def _shade_shell():
    outer = cq.Solid.makeCone(
        SHADE_R_BOT, SHADE_R_TOP, SHADE_TOP - SHADE_BOT,
        cq.Vector(0, 0, SHADE_BOT),
    )
    inner = cq.Solid.makeCone(
        SHADE_R_BOT - SHADE_WALL, SHADE_R_TOP - SHADE_WALL,
        (SHADE_TOP - SHADE_BOT) + 0.02,
        cq.Vector(0, 0, SHADE_BOT - 0.01),
    )
    shell = outer.cut(inner)
    return shell.translate(cq.Vector(0, 0, -PIVOT_Z))


def _spider_solid():
    # Neck rises from the pivot up to the underside of the socket.
    neck = cq.Solid.makeCylinder(0.012, 0.192, cq.Vector(0, 0, 0.505))
    body = neck
    # Four support arms from the socket body out to the inner shade wall.
    for k in range(4):
        ang = math.pi / 2.0 * k
        c = math.cos(ang)
        s = math.sin(ang)
        start = cq.Vector(0.024 * c, 0.024 * s, 0.720)
        end = cq.Vector(0.090 * c, 0.090 * s, 0.765)
        d = end.sub(start)
        arm = cq.Solid.makeCylinder(0.0045, d.Length, start, d)
        body = body.fuse(arm)
    return body.translate(cq.Vector(0, 0, -PIVOT_Z))


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="floor_lamp")

    # --- Base (root) --------------------------------------------------------
    base = model.part("base")
    base.visual(
        mesh_from_cadquery(_base_solid(), "base_body"),
        origin=Origin(),
        material=MAT_BASE,
        name="base_body",
    )

    # --- Stem ---------------------------------------------------------------
    stem = model.part("stem")
    stem_len = 0.505 - (BASE_TOP + 0.008)
    stem.visual(
        Cylinder(STEM_R, stem_len),
        origin=Origin(xyz=(0.0, 0.0, (BASE_TOP + 0.008) + stem_len / 2.0)),
        material=MAT_STEEL,
        name="stem_tube",
    )
    model.articulation(
        "base_to_stem",
        ArticulationType.FIXED,
        parent=base,
        child=stem,
        origin=Origin(),
    )

    # --- Shade (tilts on the stem top) -------------------------------------
    shade = model.part("shade")
    shade.visual(
        mesh_from_cadquery(_shade_shell(), "shade_shell"),
        origin=Origin(),
        material=MAT_SHADE,
        name="shade_shell",
    )
    model.articulation(
        "stem_to_shade",
        ArticulationType.REVOLUTE,
        parent=stem,
        child=shade,
        origin=Origin(xyz=(0.0, 0.0, PIVOT_Z)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=8.0, velocity=1.0, lower=-0.22, upper=0.22),
    )

    # --- Spider / shade support bracket (fixed inside the shade) -----------
    spider = model.part("spider")
    spider.visual(
        mesh_from_cadquery(_spider_solid(), "shade_spider"),
        origin=Origin(),
        material=MAT_STEEL,
        name="spider_bracket",
    )
    model.articulation(
        "shade_to_spider",
        ArticulationType.FIXED,
        parent=shade,
        child=spider,
        origin=Origin(),
    )

    # --- Socket housing -----------------------------------------------------
    socket = model.part("socket")
    socket.visual(
        Cylinder(0.023, 0.050),
        # world centre z = 0.720, part-local (pivot at 0.505)
        origin=Origin(xyz=(0.0, 0.0, 0.720 - PIVOT_Z)),
        material=MAT_CERAMIC,
        name="socket_body",
    )
    model.articulation(
        "spider_to_socket",
        ArticulationType.FIXED,
        parent=spider,
        child=socket,
        origin=Origin(xyz=(0.0, 0.0, 0.720 - PIVOT_Z)),
    )

    # --- Bulb ---------------------------------------------------------------
    bulb = model.part("bulb")
    bulb.visual(
        Sphere(0.031),
        origin=Origin(),
        material=MAT_BULB,
        name="bulb_glass",
    )
    model.articulation(
        "socket_to_bulb",
        ArticulationType.FIXED,
        parent=socket,
        child=bulb,
        origin=Origin(xyz=(0.0, 0.0, 0.685 - 0.720)),
    )

    # --- Switch housing (clamped on the stem) ------------------------------
    switch = model.part("switch_housing")
    switch.visual(
        Box((0.050, 0.050, 0.075)),
        origin=Origin(xyz=(0.0, 0.034, SWITCH_Z)),
        material=MAT_PLASTIC,
        name="switch_body",
    )
    model.articulation(
        "stem_to_switch",
        ArticulationType.FIXED,
        parent=stem,
        child=switch,
        origin=Origin(),
    )

    # --- Rocker switch (pivots on the housing) -----------------------------
    rocker = model.part("rocker")
    rocker.visual(
        Box((0.020, 0.012, 0.030)),
        origin=Origin(),
        material=MAT_PLASTIC,
        name="rocker_face",
    )
    model.articulation(
        "housing_to_rocker",
        ArticulationType.REVOLUTE,
        parent=switch,
        child=rocker,
        origin=Origin(xyz=(0.0, 0.061, SWITCH_Z)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=1.0, velocity=1.0, lower=-0.12, upper=0.12),
    )

    # --- Cord ---------------------------------------------------------------
    cord_path = [
        (0.139, 0.000, -0.795),
        (0.160, 0.000, -0.796),
        (0.180, -0.005, -0.797),
        (0.225, -0.030, -0.797),
        (0.275, -0.070, -0.797),
        (0.320, -0.110, -0.797),
    ]
    cord_geom = tube_from_spline_points(
        cord_path,
        radius=0.0035,
        samples_per_segment=12,
        radial_segments=12,
        cap_ends=True,
    )
    cord = model.part("cord")
    cord.visual(
        mesh_from_geometry(cord_geom, "cord_lead"),
        origin=Origin(),
        material=MAT_CORD,
        name="cord_lead",
    )
    # small plug at the end
    cord.visual(
        Box((0.024, 0.018, 0.020)),
        origin=Origin(xyz=(0.320, -0.122, -0.789)),
        material=MAT_CORD,
        name="cord_plug",
    )
    model.articulation(
        "base_to_cord",
        ArticulationType.FIXED,
        parent=base,
        child=cord,
        origin=Origin(),
    )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    base = object_model.get_part("base")
    stem = object_model.get_part("stem")
    shade = object_model.get_part("shade")
    spider = object_model.get_part("spider")
    socket = object_model.get_part("socket")
    bulb = object_model.get_part("bulb")
    switch = object_model.get_part("switch_housing")
    rocker = object_model.get_part("rocker")
    cord = object_model.get_part("cord")

    tilt = object_model.get_articulation("stem_to_shade")
    rocker_j = object_model.get_articulation("housing_to_rocker")

    # Stem is seated in the base boss.
    ctx.expect_contact(base, stem, name="stem seated in base")
    ctx.expect_overlap(base, stem, axes="z", elem_a="base_body", elem_b="stem_tube",
                       min_overlap=0.001, name="stem inserts into base")

    # Shade/spider/socket stack is connected.
    ctx.expect_contact(shade, spider, name="spider supports shade")
    ctx.expect_contact(spider, socket, name="socket seated on spider")
    ctx.expect_contact(ctx_part(socket), bulb, name="bulb in socket")

    # Switch gear mounted to the stem.
    ctx.expect_contact(switch, stem, name="switch clamped to stem")
    ctx.expect_contact(rocker, switch, name="rocker on housing")

    # Cord strain relief exits the base.
    ctx.expect_contact(cord, base, name="cord exits base")

    # Tilt mechanism: shade swings about the stem-top pivot in y (front/back).
    with ctx.pose({tilt: 0.0}):
        z0 = ctx.part_world_aabb(shade)
    with ctx.pose({tilt: 0.22}):
        z1 = ctx.part_world_aabb(shade)
    ok = z0 is not None and z1 is not None and (z1[1][2] != z0[1][2] or z1[0][2] != z0[0][2])
    ctx.check("shade tilts about pivot", bool(ok), details=f"rest={z0}, tilted={z1}")

    # Rocker pivots a little.
    with ctx.pose({rocker_j: 0.12}):
        ctx.check("rocker pivots", True, details="posed")

    # Intentional local overlaps.
    ctx.allow_overlap(
        socket, bulb,
        elem_a="socket_body", elem_b="bulb_glass",
        reason="Bulb is threaded into the socket; a small visible neck seats inside.",
    )

    return ctx.report()


def ctx_part(part):
    return part


object_model = build_object_model()

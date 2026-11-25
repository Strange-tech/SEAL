from __future__ import annotations

import math

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Box,
    Cylinder,
    Sphere,
    Material,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    LatheGeometry,
    ExtrudeWithHolesGeometry,
    mesh_from_geometry,
    mesh_from_cadquery,
)

# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
STEEL = Material("powder_coat_steel", rgba=(0.17, 0.17, 0.19, 1.0))
FABRIC = Material("fabric_shade", rgba=(0.90, 0.86, 0.78, 1.0))
RUBBER = Material("black_rubber", rgba=(0.035, 0.035, 0.035, 1.0))
PLASTIC = Material("black_plastic", rgba=(0.07, 0.07, 0.08, 1.0))
BRASS = Material("brass", rgba=(0.70, 0.58, 0.30, 1.0))
GLASS = Material("warm_white_glass", rgba=(1.0, 0.96, 0.82, 1.0))

# ----------------------------------------------------------------------------
# Key vertical landmarks (world y-up, object centred near origin)
# ----------------------------------------------------------------------------
BASE_BOTTOM = -0.80
BASE_TOP = -0.77
HINGE_Y = 0.55
PI2 = math.pi / 2.0
TILT = math.radians(20.0)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def circle_profile(r, n=48):
    return [
        (r * math.cos(2.0 * math.pi * i / n), r * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    ]


def _lathe_shell_yup(outer, inner, name, segments=72, y_off=0.0):
    """Hollow revolved shell; author in (radius, z) and map z -> world y."""
    g = LatheGeometry.from_shell_profiles(
        outer, inner, segments=segments, start_cap="flat", end_cap="flat"
    )
    g.vertices = [(x, z + y_off, -y) for (x, y, z) in g.vertices]
    return mesh_from_geometry(g, name)


def _annulus_yup(outer_r, inner_r, thickness, y_center, name):
    """Flat horizontal ring (spider) lying in the XZ plane at y_center."""
    g = ExtrudeWithHolesGeometry(
        circle_profile(outer_r, 64),
        [circle_profile(inner_r, 32)],
        thickness,
        center=True,
    )
    g.vertices = [(x, z + y_center, -y) for (x, y, z) in g.vertices]
    return mesh_from_geometry(g, name)


def _engrave(body, txt, fontsize, depth, cq_x, cq_y, cq_z, top=True):
    """Cut an engraved text pocket into a cadquery Workplane body."""
    t = cq.Workplane("XY").text(
        txt,
        fontsize=fontsize,
        distance=depth,
        combine=False,
        halign="center",
        valign="center",
    )
    if top:
        t = t.rotate((0, 0, 0), (0, 0, 1), 180)
    else:
        t = t.rotate((0, 0, 0), (0, 1, 0), 180)
    t = t.translate((cq_x, cq_y, cq_z))
    return body.cut(t)


# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------
def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="floor_lamp")

    # ---- Base (root) -------------------------------------------------------
    base_wp = cq.Workplane("XY").circle(0.15).extrude(0.03)
    base_wp = _engrave(base_wp, "Manufacturer", 0.012, 0.0009, 0.0, -0.035, 0.0009, top=False)
    base_wp = _engrave(base_wp, "Model No.", 0.012, 0.0009, 0.0, 0.032, 0.0009, top=False)
    base_mesh = mesh_from_cadquery(base_wp.val(), "base_body")

    base = model.part("base")
    base.visual(
        base_mesh,
        origin=Origin(xyz=(0.0, BASE_BOTTOM, 0.0)),
        material=STEEL,
        name="base_body",
    )

    # ---- Stem (fixed to base) ---------------------------------------------
    stem = model.part("stem")
    stem.visual(
        Cylinder(0.0125, 1.30),
        origin=Origin(xyz=(0.0, -0.12, 0.0), rpy=(-PI2, 0.0, 0.0)),
        material=STEEL,
        name="pole",
    )
    stem.visual(
        Cylinder(0.020, 0.020),
        origin=Origin(xyz=(0.0, -0.76, 0.0), rpy=(-PI2, 0.0, 0.0)),
        material=STEEL,
        name="collar",
    )
    stem.visual(
        Cylinder(0.019, 0.050),
        origin=Origin(xyz=(0.0, 0.535, 0.0), rpy=(0.0, PI2, 0.0)),
        material=STEEL,
        name="knuckle",
    )

    model.articulation(
        "base_to_stem",
        ArticulationType.FIXED,
        parent=base,
        child=stem,
    )

    # ---- Shade head (tilting) ---------------------------------------------
    shade = model.part("shade")
    shade_mesh = _lathe_shell_yup(
        [(0.175, 0.02), (0.034, 0.24)],
        [(0.171, 0.02), (0.030, 0.24)],
        "shade_shell",
    )
    shade.visual(shade_mesh, origin=Origin(), material=FABRIC, name="shade_shell")
    shade.visual(
        Cylinder(0.010, 0.21),
        origin=Origin(xyz=(0.0, 0.085, 0.0), rpy=(-PI2, 0.0, 0.0)),
        material=STEEL,
        name="neck",
    )
    shade.visual(
        _annulus_yup(0.068, 0.010, 0.004, 0.18, "spider"),
        origin=Origin(),
        material=STEEL,
        name="spider",
    )

    model.articulation(
        "stem_to_shade",
        ArticulationType.REVOLUTE,
        parent=stem,
        child=shade,
        origin=Origin(xyz=(0.0, HINGE_Y, 0.0)),
        axis=(1.0, 0.0, 0.0),
        motion_limits=MotionLimits(effort=6.0, velocity=2.0, lower=-TILT, upper=TILT),
    )

    # ---- Socket cup (fixed inside shade) ----------------------------------
    socket = model.part("socket")
    socket.visual(
        Cylinder(0.034, 0.060),
        origin=Origin(xyz=(0.0, 0.02, 0.0), rpy=(-PI2, 0.0, 0.0)),
        material=PLASTIC,
        name="socket_cup",
    )
    socket.visual(
        Cylinder(0.016, 0.022),
        origin=Origin(xyz=(0.0, -0.025, 0.0), rpy=(-PI2, 0.0, 0.0)),
        material=BRASS,
        name="socket_shell",
    )
    model.articulation(
        "shade_to_socket",
        ArticulationType.FIXED,
        parent=shade,
        child=socket,
        origin=Origin(xyz=(0.0, 0.19, 0.0)),
    )

    # ---- Bulb (threaded into socket) --------------------------------------
    bulb = model.part("bulb")
    bulb.visual(
        Cylinder(0.014, 0.022),
        origin=Origin(xyz=(0.0, 0.0, 0.0), rpy=(-PI2, 0.0, 0.0)),
        material=BRASS,
        name="bulb_base",
    )
    bulb.visual(
        Sphere(0.045),
        origin=Origin(xyz=(0.0, -0.055, 0.0)),
        material=GLASS,
        name="bulb_glass",
    )
    model.articulation(
        "socket_to_bulb",
        ArticulationType.FIXED,
        parent=socket,
        child=bulb,
        origin=Origin(xyz=(0.0, -0.02, 0.0)),
    )

    # ---- Cord + foot switch + plug (fixed accessory) ----------------------
    cord = model.part("cord_assembly")
    cord.visual(
        Cylinder(0.0035, 0.0125),
        origin=Origin(xyz=(0.0, -0.7965, 0.15125)),
        material=RUBBER,
        name="cord",
    )
    cord.visual(
        Cylinder(0.0035, 0.0055),
        origin=Origin(xyz=(0.0, -0.7965, 0.19525)),
        material=RUBBER,
        name="cord_tail",
    )

    sw_wp = cq.Workplane("XY").rect(0.045, 0.035).extrude(0.028)
    sw_wp = sw_wp.union(
        cq.Workplane("XY").rect(0.034, 0.026).extrude(0.006).translate((0, 0, 0.028))
    )
    sw_wp = _engrave(sw_wp, "ON", 0.006, 0.0007, 0.010, 0.0, 0.0332, top=True)
    sw_wp = _engrave(sw_wp, "OFF", 0.005, 0.0007, -0.010, 0.0, 0.0332, top=True)
    sw_mesh = mesh_from_cadquery(sw_wp.val(), "foot_switch")
    cord.visual(
        sw_mesh,
        origin=Origin(xyz=(0.0, -0.80, 0.175)),
        material=PLASTIC,
        name="foot_switch",
    )

    pl_wp = cq.Workplane("XY").rect(0.030, 0.020).extrude(0.018)
    pl_wp = _engrave(pl_wp, "120 V", 0.0035, 0.0006, 0.0, -0.0038, 0.0174, top=True)
    pl_wp = _engrave(pl_wp, "60 Hz", 0.0035, 0.0006, 0.0, 0.0040, 0.0174, top=True)
    pl_mesh = mesh_from_cadquery(pl_wp.val(), "plug")
    cord.visual(
        pl_mesh,
        origin=Origin(xyz=(0.0, -0.80, 0.208)),
        material=PLASTIC,
        name="plug",
    )

    model.articulation(
        "base_to_cord",
        ArticulationType.FIXED,
        parent=base,
        child=cord,
    )

    return model


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------
def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    base = object_model.get_part("base")
    stem = object_model.get_part("stem")
    shade = object_model.get_part("shade")
    socket = object_model.get_part("socket")
    bulb = object_model.get_part("bulb")
    cord = object_model.get_part("cord_assembly")
    tilt = object_model.get_articulation("stem_to_shade")

    # Intentional, mechanically-explanatory local overlaps.
    ctx.allow_overlap(
        stem, shade, elem_a="knuckle", elem_b="neck",
        reason="The shade neck is captured inside the hinge knuckle.",
    )
    ctx.allow_overlap(
        shade, socket, elem_a="shade_shell", elem_b="socket_cup",
        reason="The socket cup is seated through the shade top opening.",
    )
    ctx.allow_overlap(
        shade, bulb, elem_a="shade_shell", elem_b="bulb_glass",
        reason="The bulb hangs nested inside the fabric shade.",
    )
    ctx.allow_overlap(
        socket, bulb, elem_a="socket_shell", elem_b="bulb_base",
        reason="The bulb thread is screwed into the socket shell.",
    )
    ctx.allow_overlap(
        base, cord, elem_a="base_body", elem_b="cord",
        reason="The supply cord exits under the base rim.",
    )

    # Support / seating proofs.
    ctx.expect_contact(base, stem, elem_a="base_body", elem_b="collar",
                       name="stem collar seats on base")
    ctx.expect_contact(shade, socket, elem_a="shade_shell", elem_b="socket_cup",
                       name="socket seated in shade top")
    ctx.expect_contact(socket, bulb, elem_a="socket_shell", elem_b="bulb_base",
                       name="bulb engaged in socket")
    ctx.expect_contact(base, cord, elem_a="base_body", elem_b="cord",
                       name="cord attached to base")

    # Bulb nests inside the shade footprint.
    ctx.expect_overlap(shade, bulb, axes="xz", elem_a="shade_shell",
                       elem_b="bulb_glass", min_overlap=0.02,
                       name="bulb within shade footprint")

    # Tilt mechanism: positive q pitches the head toward +Z (front).
    with ctx.pose({tilt: TILT}):
        aabb_fwd = ctx.part_element_world_aabb(shade, elem="shade_shell")
    with ctx.pose({tilt: -TILT}):
        aabb_back = ctx.part_element_world_aabb(shade, elem="shade_shell")

    fwd_z = aabb_fwd[1][2] if aabb_fwd else None
    back_z = aabb_back[1][2] if aabb_back else None
    ctx.check(
        "shade tilts toward front on positive q",
        fwd_z is not None and back_z is not None and fwd_z > back_z + 0.02,
        details=f"fwd_max_z={fwd_z}, back_max_z={back_z}",
    )

    return ctx.report()


object_model = build_object_model()

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

# ----------------------------------------------------------------------------
# TV with swivel stand.  Scene frame: y-up, +z forward (screen faces +z).
# ----------------------------------------------------------------------------
BASE_W = 0.30
BASE_D = 0.22
BASE_H = 0.025

NECK_W = 0.11
NECK_H = 0.06
NECK_D = 0.055

DISP_W = 1.23
DISP_H = 0.70
DISP_D = 0.08

BOTTOM_Y = -0.3925
BASE_CY = BOTTOM_Y + BASE_H / 2.0          # -0.380
BASE_TOP = BOTTOM_Y + BASE_H               # -0.3675
NECK_CY = BASE_TOP + NECK_H / 2.0          # -0.3375
PIVOT_Y = BASE_TOP + NECK_H                # -0.3075
DISPLAY_LOCAL_CY = DISP_H / 2.0            # display geometry centre offset in part frame

SWIVEL_LIMIT = math.radians(30.0)

PI = math.pi


def _rounded_rect_solid(w: float, d: float, r: float, h: float) -> cq.Workplane:
    """Rounded-rectangle solid extruded along +Z, thickness h (centred)."""
    sk = cq.Sketch().rect(w, d).vertices().fillet(r)
    return cq.Workplane("XY").placeSketch(sk).extrude(h)


def _text_solid(txt: str, fontsize: float, distance: float) -> cq.Workplane:
    return cq.Workplane("XY").text(
        txt, fontsize=fontsize, distance=distance, combine=False
    )


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="swivel_tv")

    matte_black = model.material("matte_black", rgba=(0.045, 0.045, 0.050, 1.0))
    graphite = model.material("graphite", rgba=(0.11, 0.11, 0.12, 1.0))
    screen_glass = model.material("screen_glass", rgba=(0.015, 0.018, 0.025, 1.0))
    label_grey = model.material("label_grey", rgba=(0.62, 0.62, 0.64, 1.0))

    # ------------------------------------------------------------------ base
    stand_base = model.part("stand_base")
    base_shape = (
        _rounded_rect_solid(BASE_W, BASE_D, 0.025, BASE_H)
        .rotate((0, 0, 0), (1, 0, 0), -90)          # lay flat: thickness -> +Y
        .translate((0, BOTTOM_Y, 0))
    )
    stand_base.visual(
        mesh_from_cadquery(base_shape, "tv_stand_base"),
        material=matte_black,
        name="base_slab",
    )

    # ------------------------------------------------------------------ neck
    stand_neck = model.part("stand_neck")
    stand_neck.visual(
        Box((NECK_W, NECK_H, NECK_D)),
        origin=Origin(xyz=(0.0, NECK_CY, 0.0)),
        material=graphite,
        name="neck_column",
    )
    # swivel collar sitting right under the display
    stand_neck.visual(
        Cylinder(radius=0.05, length=0.010),
        origin=Origin(xyz=(0.0, PIVOT_Y - 0.005, 0.0), rpy=(-PI / 2.0, 0.0, 0.0)),
        material=matte_black,
        name="swivel_collar",
    )
    stand_neck.visual(
        Cylinder(radius=0.032, length=0.004),
        origin=Origin(xyz=(0.0, PIVOT_Y - 0.001, 0.0), rpy=(-PI / 2.0, 0.0, 0.0)),
        material=graphite,
        name="swivel_cap",
    )

    # --------------------------------------------------------------- display
    display = model.part("display")

    # body shell + rear electronics housing, fused into one solid
    body = cq.Workplane("XY").box(DISP_W, DISP_H, DISP_D).edges("|Z").fillet(0.02)
    rear_housing = (
        cq.Workplane("XY")
        .box(0.44, 0.26, 0.045)
        .edges("|Z")
        .fillet(0.02)
        .translate((0.0, -0.05, -0.06))
    )
    body = body.union(rear_housing)

    # recessed screen pocket cut into the front (+z) face
    pocket = (
        _rounded_rect_solid(1.19, 0.60, 0.015, 0.02).translate((0.0, 0.035, 0.03))
    )
    body = body.cut(pocket)

    display.visual(
        mesh_from_cadquery(body, "tv_display_body"),
        origin=Origin(xyz=(0.0, DISPLAY_LOCAL_CY, 0.0)),
        material=matte_black,
        name="display_body",
    )

    # glossy screen panel seated in the pocket (front recessed below bezel)
    display.visual(
        Box((1.18, 0.59, 0.006)),
        origin=Origin(xyz=(0.0, DISPLAY_LOCAL_CY + 0.035, 0.033)),
        material=screen_glass,
        name="screen_panel",
    )

    # front bottom-chin wordmark
    wordmark = _text_solid("TV", 0.032, 0.0012).translate((0.0, 0.0425, 0.039))
    display.visual(
        mesh_from_cadquery(wordmark, "tv_wordmark"),
        material=label_grey,
        name="wordmark",
    )

    # rear moulded labels (readable from behind: build facing +z then flip 180 deg about Y)
    label_specs = (
        ("MODEL", 0.36),
        ("SERIAL", 0.30),
        ("INPUT", 0.24),
    )
    for idx, (txt, ly) in enumerate(label_specs):
        solid = (
            _text_solid(txt, 0.013, 0.0012)
            .rotate((0, 0, 0), (0, 1, 0), 180)
            .translate((0.0, ly, -0.0795))
        )
        display.visual(
            mesh_from_cadquery(solid, f"tv_rear_label_{idx}"),
            material=label_grey,
            name=f"rear_label_{idx}",
        )

    # ----------------------------------------------------------- articulations
    model.articulation(
        "base_to_neck",
        ArticulationType.FIXED,
        parent=stand_base,
        child=stand_neck,
        origin=Origin(xyz=(0.0, 0.0, 0.0)),
    )

    model.articulation(
        "neck_to_display",
        ArticulationType.REVOLUTE,
        parent=stand_neck,
        child=display,
        origin=Origin(xyz=(0.0, PIVOT_Y, 0.0)),
        axis=(0.0, 1.0, 0.0),
        motion_limits=MotionLimits(
            effort=40.0,
            velocity=0.6,
            lower=-SWIVEL_LIMIT,
            upper=SWIVEL_LIMIT,
        ),
    )

    return model


def _aabb_size(aabb):
    mins, maxs = aabb
    return (
        float(maxs[0] - mins[0]),
        float(maxs[1] - mins[1]),
        float(maxs[2] - mins[2]),
    )


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    base = object_model.get_part("stand_base")
    neck = object_model.get_part("stand_neck")
    display = object_model.get_part("display")
    swivel = object_model.get_articulation("neck_to_display")

    ctx.check("display_part_present", display is not None, "display part missing")
    ctx.check("neck_part_present", neck is not None, "neck part missing")
    ctx.check("base_part_present", base is not None, "base part missing")

    # support / seating chain
    ctx.expect_contact(neck, base, contact_tol=5e-4, name="neck seated on base")
    ctx.expect_contact(display, neck, contact_tol=5e-4, name="display seated on neck")

    # proportions
    disp_aabb = ctx.part_world_aabb(display)
    if disp_aabb is not None:
        dx, dy, dz = _aabb_size(disp_aabb)
        ctx.check("display_width", 1.20 <= dx <= 1.26, f"width={dx:.3f}")
        ctx.check("display_height", 0.68 <= dy <= 0.72, f"height={dy:.3f}")
        ctx.check("display_depth", 0.06 <= dz <= 0.20, f"depth={dz:.3f}")

    base_aabb = ctx.part_world_aabb(base)
    if base_aabb is not None:
        bdx, bdy, bdz = _aabb_size(base_aabb)
        ctx.check(
            "base_footprint",
            0.27 <= bdx <= 0.33 and 0.19 <= bdz <= 0.25,
            f"base={bdx:.3f}x{bdz:.3f}",
        )
        ctx.check("base_thin", 0.02 <= bdy <= 0.04, f"base_h={bdy:.3f}")

    # swivel limits and motion (rotating the wide thin panel increases its depth footprint)
    limits = swivel.motion_limits
    ctx.check(
        "swivel_plus_minus_30",
        limits is not None
        and abs(limits.lower + SWIVEL_LIMIT) < 1e-6
        and abs(limits.upper - SWIVEL_LIMIT) < 1e-6,
        f"limits={limits!r}",
    )

    if disp_aabb is not None and limits is not None:
        rest_depth = _aabb_size(disp_aabb)[2]
        with ctx.pose({swivel: limits.upper}):
            turned = ctx.part_world_aabb(display)
            turned_depth = _aabb_size(turned)[2] if turned is not None else rest_depth
        ctx.check(
            "swivel_rotates_display",
            turned_depth > rest_depth + 0.15,
            f"rest_depth={rest_depth:.3f}, turned_depth={turned_depth:.3f}",
        )

    return ctx.report()


object_model = build_object_model()

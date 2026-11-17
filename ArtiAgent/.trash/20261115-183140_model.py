from __future__ import annotations

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Cylinder,
    Material,
    MeshGeometry,
    Origin,
    TestContext,
    TestReport,
    mesh_from_geometry,
    tessellate_cadquery,
)

import math

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
UPHOLSTERY = Material(name="upholstery", rgba=(0.36, 0.38, 0.42, 1.0))
CUSHION = Material(name="cushion", rgba=(0.44, 0.46, 0.50, 1.0))
LEG_WOOD = Material(name="leg_wood", rgba=(0.16, 0.10, 0.06, 1.0))

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _rounded_slab_mesh(w, d, h, rc, re, center, name):
    """A soft upholstered slab: rounded footprint corners + rounded top/bottom
    rims.  w = width (x), d = depth (z), h = height (y).  Built in CadQuery's
    z-up convention, then re-expressed in the y-up world frame."""
    rc = min(rc, 0.45 * w, 0.45 * d)
    re = min(re, 0.45 * h, 0.45 * rc)

    sk = cq.Sketch().rect(w, d).vertices().fillet(rc)
    wp = cq.Workplane("XY").placeSketch(sk).extrude(h)

    rim_edges = [
        e
        for e in wp.edges().vals()
        if abs(e.Center().z) < 1e-6 or abs(e.Center().z - h) < 1e-6
    ]
    wp = wp.newObject(rim_edges).fillet(re)

    verts, faces = tessellate_cadquery(wp, tolerance=0.0008)

    # cq (x, y, z) -> y-up world (x, z, -y)
    yv = [(x, z, -y) for (x, y, z) in verts]
    xs = [p[0] for p in yv]
    ys = [p[1] for p in yv]
    zs = [p[2] for p in yv]
    cx0 = 0.5 * (min(xs) + max(xs))
    cy0 = 0.5 * (min(ys) + max(ys))
    cz0 = 0.5 * (min(zs) + max(zs))
    dx, dy, dz = center[0] - cx0, center[1] - cy0, center[2] - cz0
    verts2 = [(x + dx, y + dy, z + dz) for (x, y, z) in yv]

    geom = MeshGeometry(vertices=verts2, faces=faces)
    return mesh_from_geometry(geom, name)


# ---------------------------------------------------------------------------
# Key elevations / sizes (metres)
# ---------------------------------------------------------------------------
HALF_W = 1.00          # overall half width
FLOOR = -0.425         # bottom of legs
TOTAL_TOP = 0.425      # top of backrest
LEG_H = 0.09
LEG_R = 0.028
LEG_TOP = FLOOR + LEG_H               # -0.335
BASE_BOT = LEG_TOP                    # -0.335
BASE_TOP = -0.135
BASE_W = 1.72
BASE_D = 0.86

SEAT_TOP = 0.015
SEAT_Z0, SEAT_Z1 = -0.25, 0.42

ARM_TOP = 0.175
ARM_IN = 0.84
ARM_W = HALF_W - ARM_IN               # 0.16

BACK_TOP = TOTAL_TOP
BACK_Z0, BACK_Z1 = -0.43, -0.25


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="three_seat_sofa")

    parts = {}

    def slab_part(name, w, d, h, rc, re, cx, cy, cz, mat):
        p = model.part(name)
        m = _rounded_slab_mesh(w, d, h, rc, re, (cx, cy, cz), name + "_shell")
        p.visual(m, origin=Origin(), material=mat, name=name + "_shell")
        parts[name] = p
        return p

    # Root: upholstered seat frame / base -----------------------------------
    base = slab_part(
        "base_frame", BASE_W, BASE_D, BASE_TOP - BASE_BOT,
        0.06, 0.022, 0.0, 0.5 * (BASE_BOT + BASE_TOP), 0.0, UPHOLSTERY,
    )

    # Legs ------------------------------------------------------------------
    for i, (lx, lz) in enumerate(
        [(-0.80, 0.32), (0.80, 0.32), (-0.80, -0.32), (0.80, -0.32)]
    ):
        p = model.part(f"leg_{i}")
        p.visual(
            Cylinder(radius=LEG_R, length=LEG_H),
            origin=Origin(xyz=(lx, 0.5 * (FLOOR + LEG_TOP), lz), rpy=(-math.pi / 2, 0.0, 0.0)),
            material=LEG_WOOD,
            name=f"leg_{i}_post",
        )
        parts[f"leg_{i}"] = p

    # Armrests --------------------------------------------------------------
    for i, sgn in enumerate((-1.0, 1.0)):
        slab_part(
            f"armrest_{i}", ARM_W, BASE_D, ARM_TOP - BASE_TOP,
            0.055, 0.035, sgn * (ARM_IN + 0.5 * ARM_W),
            0.5 * (BASE_TOP + ARM_TOP), 0.0, UPHOLSTERY,
        )

    # Backrest --------------------------------------------------------------
    slab_part(
        "backrest", 2.0 * ARM_IN, BACK_Z1 - BACK_Z0, BACK_TOP - BASE_TOP,
        0.05, 0.035, 0.0, 0.5 * (BASE_TOP + BACK_TOP),
        0.5 * (BACK_Z0 + BACK_Z1), UPHOLSTERY,
    )

    # Seat cushions (two) ---------------------------------------------------
    seat_w = 0.79
    seat_d = SEAT_Z1 - SEAT_Z0
    seat_cz = 0.5 * (SEAT_Z0 + SEAT_Z1)
    for i, cx in enumerate((-0.40, 0.40)):
        slab_part(
            f"seat_cushion_{i}", seat_w, seat_d, SEAT_TOP - BASE_TOP,
            0.075, 0.045, cx, 0.5 * (BASE_TOP + SEAT_TOP), seat_cz, CUSHION,
        )

    # Back cushions (two) ---------------------------------------------------
    bc_w = 0.78
    bc_h = 0.33
    bc_thick = 0.16
    bc_z0 = BACK_Z1
    bc_z1 = BACK_Z1 + bc_thick
    bc_cy = SEAT_TOP + 0.5 * bc_h
    for i, cx in enumerate((-0.40, 0.40)):
        slab_part(
            f"back_cushion_{i}", bc_w, bc_thick, bc_h,
            0.06, 0.05, cx, bc_cy, 0.5 * (bc_z0 + bc_z1), CUSHION,
        )

    # ------------------------------------------------------------------
    # Fixed joints: everything mounted to the base frame.
    # ------------------------------------------------------------------
    fixed = []
    for name, p in parts.items():
        if name == "base_frame":
            continue
        jn = f"base_frame_to_{name}"
        model.articulation(
            jn,
            ArticulationType.FIXED,
            parent=base,
            child=p,
            origin=Origin(),
        )
        fixed.append(jn)

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    base = object_model.get_part("base_frame")

    # Every component sits on / against the base or the cushions it rests on.
    for name in (
        "leg_0", "leg_1", "leg_2", "leg_3",
        "armrest_0", "armrest_1", "backrest",
        "seat_cushion_0", "seat_cushion_1",
    ):
        ctx.expect_contact(base, object_model.get_part(name), name=f"{name}_contacts_base")

    # Back cushions rest on the seat cushions and lean on the backrest.
    for i in range(2):
        ctx.expect_contact(
            object_model.get_part(f"back_cushion_{i}"),
            object_model.get_part(f"seat_cushion_{i}"),
            name=f"back_cushion_{i}_rests_on_seat",
        )
        ctx.expect_contact(
            object_model.get_part(f"back_cushion_{i}"),
            object_model.get_part("backrest"),
            name=f"back_cushion_{i}_rests_on_backrest",
        )

    # Overall proportions.
    amin = [1e9, 1e9, 1e9]
    amax = [-1e9, -1e9, -1e9]
    for p in object_model.parts:
        bb = ctx.part_world_aabb(p)
        if bb is None:
            continue
        for k in range(3):
            amin[k] = min(amin[k], bb[0][k])
            amax[k] = max(amax[k], bb[1][k])

    width = amax[0] - amin[0]
    height = amax[1] - amin[1]
    depth = amax[2] - amin[2]
    ctx.check("width_near_2m", 1.9 <= width <= 2.1, details=f"width={width:.3f}")
    ctx.check("height_near_085m", 0.80 <= height <= 0.90, details=f"height={height:.3f}")
    ctx.check("depth_near_09m", 0.80 <= depth <= 0.95, details=f"depth={depth:.3f}")

    # Seat sits lower than armrests, which sit lower than the backrest.
    def top_of(name):
        bb = ctx.part_world_aabb(object_model.get_part(name))
        return bb[1][1]

    ctx.check(
        "seat_below_arm_above_back_ordering",
        top_of("seat_cushion_0") < top_of("armrest_0") < top_of("backrest"),
        details=f"seat={top_of('seat_cushion_0'):.3f} arm={top_of('armrest_0'):.3f} back={top_of('backrest'):.3f}",
    )

    return ctx.report()


object_model = build_object_model()

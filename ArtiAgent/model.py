from __future__ import annotations

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Box,
    Material,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    mesh_from_cadquery,
)

# ---------------------------------------------------------------------------
# Overall envelope (metres). Front face of the cabinet points toward +Y.
# ---------------------------------------------------------------------------
W = 0.700          # carcass width  (x: -0.350 .. +0.350)
D = 0.580          # carcass depth  (y: -0.290 .. +0.290)
H = 0.840          # carcass height (z:  0.000 .. +0.840)
WALL = 0.018       # panel thickness
FRONT_FACE = D / 2.0

# Face-frame openings (cut through the 20 mm front frame plate)
DOOR_OPEN = (-0.035, 0.295, 0.060, 0.800)     # x0, x1, z0, z1
DRW_OPEN = (-0.295, -0.080, 0.060, 0.800)     # x0, x1, z0, z1

# Door leaf (in the door part frame, hinge line at local x = 0)
DOOR_W = 0.336
DOOR_T = 0.019
DOOR_H = 0.740
DOOR_SEAT = 0.0005        # slight embed into the face-frame plane (hidden)

# Drawer stack: four fronts filling the drawer opening
DRW_PANEL_W = 0.221
DRW_PANEL_H = 0.1805
DRW_GAP = 0.006
DRW_T = 0.019
DRW_BOX_W = 0.200
DRW_BOX_H = 0.110
DRW_BOX_D = 0.500
DRW_TRAVEL = 0.320


def _box(x0, y0, z0, dx, dy, dz) -> cq.Solid:
    return cq.Solid.makeBox(dx, dy, dz, cq.Vector(x0, y0, z0))


# ---------------------------------------------------------------------------
# Carcass: hollow shell + 20 mm face frame with two openings + divider + shelf
# ---------------------------------------------------------------------------
def _carcass_solid() -> cq.Solid:
    outer = _box(-W / 2, -D / 2, 0.0, W, D, H)
    void = _box(
        -W / 2 + WALL, -D / 2 + WALL, WALL,
        W - 2 * WALL, D - 2 * WALL, H - 2 * WALL,
    )
    door_open = _box(
        DOOR_OPEN[0], FRONT_FACE - 0.040, DOOR_OPEN[2],
        DOOR_OPEN[1] - DOOR_OPEN[0], 0.050, DOOR_OPEN[3] - DOOR_OPEN[2],
    )
    drw_open = _box(
        DRW_OPEN[0], FRONT_FACE - 0.040, DRW_OPEN[2],
        DRW_OPEN[1] - DRW_OPEN[0], 0.050, DRW_OPEN[3] - DRW_OPEN[2],
    )
    shell = outer.cut(void).cut(door_open).cut(drw_open)

    # vertical divider between the door bay and the drawer bay
    divider = _box(-0.066, -D / 2 + WALL, WALL, WALL, D - 2 * WALL, H - 2 * WALL)

    # one fixed interior shelf in the door bay
    shelf = _box(-0.048, -D / 2 + WALL, 0.420, 0.380, D - 2 * WALL, WALL)

    return shell.fuse(divider).fuse(shelf)


def _countertop_solid() -> cq.Solid:
    # caps the carcass, overhangs slightly, embeds 2 mm into the carcass top
    return _box(-W / 2 - 0.020, -D / 2 - 0.010, H - 0.002, W + 0.040, D + 0.032, 0.037)


# ---------------------------------------------------------------------------
# Shaker door leaf, authored in the door part frame (hinge line at x = 0)
# ---------------------------------------------------------------------------
def _door_solid() -> cq.Solid:
    leaf = _box(-DOOR_W, -DOOR_SEAT, 0.0, DOOR_W, DOOR_T + DOOR_SEAT, DOOR_H)
    # recessed centre field on the front face -> shaker look
    recess = _box(-DOOR_W + 0.024, 0.011, 0.024, DOOR_W - 0.048, 0.012, DOOR_H - 0.048)
    return leaf.cut(recess)


def _door_pull_solid() -> cq.Solid:
    # small dark vertical pull near the door's free (right) edge, upper area
    bar = _box(-0.307, 0.028, 0.600, 0.014, 0.010, 0.110)
    stand_a = _box(-0.303, 0.010, 0.615, 0.006, 0.019, 0.014)
    stand_b = _box(-0.303, 0.010, 0.681, 0.006, 0.019, 0.014)
    return bar.fuse(stand_a).fuse(stand_b)


# ---------------------------------------------------------------------------
# Drawer front + hollow drawer box, authored in the drawer part frame
# ---------------------------------------------------------------------------
def _drawer_front_solid() -> cq.Solid:
    panel = _box(
        -DRW_PANEL_W / 2, -DRW_SEAT, -DRW_PANEL_H / 2,
        DRW_PANEL_W, DRW_T + DRW_SEAT, DRW_PANEL_H,
    )
    field = _box(
        -DRW_PANEL_W / 2 + 0.018, 0.015, -DRW_PANEL_H / 2 + 0.016,
        DRW_PANEL_W - 0.036, 0.010, DRW_PANEL_H - 0.032,
    )
    return panel.cut(field)


DRW_SEAT = DOOR_SEAT


def _drawer_box_solid() -> cq.Solid:
    # front of the box is tucked 0.5 mm into the front panel
    outer = _box(-DRW_BOX_W / 2, -(DRW_BOX_D + 0.001), -DRW_BOX_H / 2,
                 DRW_BOX_W, DRW_BOX_D + 0.0005, DRW_BOX_H)
    inner = _box(-DRW_BOX_W / 2 + 0.012, -(DRW_BOX_D + 0.001) + 0.012,
                 -DRW_BOX_H / 2 + 0.012,
                 DRW_BOX_W - 0.024, DRW_BOX_D - 0.024, DRW_BOX_H)
    return outer.cut(inner)


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="wooden_cabinet_with_drawers")

    wood_carcass = model.material("oak_carcass", rgba=(0.46, 0.30, 0.16, 1.0))
    wood_door = model.material("oak_door", rgba=(0.52, 0.35, 0.19, 1.0))
    wood_drawer = model.material("oak_drawer", rgba=(0.56, 0.38, 0.21, 1.0))
    wood_top = model.material("light_top", rgba=(0.74, 0.65, 0.48, 1.0))
    dark_metal = model.material("dark_metal", rgba=(0.10, 0.10, 0.11, 1.0))

    # ---------------- carcass (root, fixed) ----------------
    carcass = model.part("carcass")
    carcass.visual(
        mesh_from_cadquery(_carcass_solid(), "carcass_body"),
        name="carcass_body",
        material=wood_carcass,
    )
    carcass.visual(
        mesh_from_cadquery(_countertop_solid(), "countertop"),
        name="countertop",
        material=wood_top,
    )

    # ---------------- hinged door over the left bay ----------------
    door = model.part("door")
    door.visual(
        mesh_from_cadquery(_door_solid(), "door_leaf"),
        name="door_leaf",
        material=wood_door,
    )
    door.visual(
        mesh_from_cadquery(_door_pull_solid(), "door_pull"),
        name="door_pull",
        material=dark_metal,
    )

    model.articulation(
        "carcass_to_door",
        ArticulationType.REVOLUTE,
        parent=carcass,
        child=door,
        # hinge line on the outer (+X) edge of the door, on the frame front plane
        origin=Origin(xyz=(0.298, FRONT_FACE - DOOR_SEAT, 0.058)),
        # leaf extends along -X from the hinge; -Z makes positive q swing it out
        axis=(0.0, 0.0, -1.0),
        motion_limits=MotionLimits(effort=25.0, velocity=1.5, lower=0.0, upper=1.55),
    )

    # ---------------- four drawers in the right bay ----------------
    centres = (
        0.800 - DRW_PANEL_H / 2,
        0.800 - DRW_PANEL_H - DRW_GAP - DRW_PANEL_H / 2,
        0.800 - 2 * (DRW_PANEL_H + DRW_GAP) - DRW_PANEL_H / 2,
        0.800 - 3 * (DRW_PANEL_H + DRW_GAP) - DRW_PANEL_H / 2,
    )
    names = ("top_drawer", "upper_drawer", "lower_drawer", "bottom_drawer")
    bay_centre_x = (DRW_OPEN[0] + DRW_OPEN[1]) / 2.0

    for name, cz in zip(names, centres):
        drawer = model.part(name)
        drawer.visual(
            mesh_from_cadquery(_drawer_front_solid(), name + "_front"),
            name="drawer_front",
            material=wood_drawer,
        )
        drawer.visual(
            mesh_from_cadquery(_drawer_box_solid(), name + "_box"),
            name="drawer_box",
            material=wood_carcass,
        )
        model.articulation(
            "carcass_to_" + name,
            ArticulationType.PRISMATIC,
            parent=carcass,
            child=drawer,
            origin=Origin(xyz=(bay_centre_x, FRONT_FACE - DRW_SEAT, cz)),
            axis=(0.0, 1.0, 0.0),
            motion_limits=MotionLimits(
                effort=120.0, velocity=0.30, lower=0.0, upper=DRW_TRAVEL
            ),
        )

    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    carcass = object_model.get_part("carcass")
    door = object_model.get_part("door")
    door_hinge = object_model.get_articulation("carcass_to_door")
    drawers = [
        object_model.get_part(n)
        for n in ("top_drawer", "upper_drawer", "lower_drawer", "bottom_drawer")
    ]
    slides = [object_model.get_articulation("carcass_to_" + d.name) for d in drawers]

    # --- door is seated on the face frame (only a hidden seating embed) ---
    ctx.expect_gap(
        door, carcass,
        axis="y",
        positive_elem="door_leaf",
        negative_elem="carcass_body",
        max_gap=0.0025,
        max_penetration=0.0025,
        name="door sits on the face frame plane",
    )
    ctx.expect_overlap(
        door, carcass,
        axes="xz",
        elem_a="door_leaf",
        elem_b="carcass_body",
        min_overlap=0.20,
        name="door covers the door opening",
    )

    # --- every drawer front is seated on the face frame ---
    for drawer in drawers:
        ctx.expect_gap(
            drawer, carcass,
            axis="y",
            positive_elem="drawer_front",
            negative_elem="carcass_body",
            max_gap=0.0025,
            max_penetration=0.0025,
            name=f"{drawer.name} front sits on the face frame",
        )

    # --- door opens outward about its vertical hinge ---
    rest_door = ctx.part_element_world_aabb(door, elem="door_leaf")
    with ctx.pose({door_hinge: door_hinge.motion_limits.upper}):
        open_door = ctx.part_element_world_aabb(door, elem="door_leaf")
        ctx.expect_gap(
            door, carcass,
            axis="y",
            positive_elem="door_leaf",
            negative_elem="carcass_body",
            max_gap=0.0,
            max_penetration=0.002,
            name="open door does not bear into the face frame",
        )
    ctx.check(
        "door swings forward when opened",
        rest_door is not None and open_door is not None
        and open_door[1][1] > rest_door[1][1] + 0.25,
        details=f"rest={rest_door}, open={open_door}",
    )

    # --- each drawer pulls out toward the viewer and stays engaged ---
    for drawer, slide in zip(drawers, slides):
        rest = ctx.part_world_position(drawer)
        with ctx.pose({slide: DRW_TRAVEL}):
            extended = ctx.part_world_position(drawer)
            box_aabb = ctx.part_element_world_aabb(drawer, elem="drawer_box")
        ctx.check(
            f"{drawer.name} pulls out toward the viewer",
            rest is not None and extended is not None
            and extended[1] > rest[1] + 0.30,
            details=f"rest={rest}, extended={extended}",
        )
        ctx.check(
            f"{drawer.name} box stays in the carcass at full extension",
            box_aabb is not None and box_aabb[0][1] < 0.27,
            details=f"box_aabb={box_aabb}",
        )

    # --- drawers are fully inserted along the slide axis at rest ---
    ctx.expect_overlap(
        drawers[3], carcass,
        axes="y",
        elem_a="drawer_box",
        elem_b="carcass_body",
        min_overlap=0.40,
        name="collapsed drawer box is deeply inserted",
    )

    return ctx.report()


object_model = build_object_model()

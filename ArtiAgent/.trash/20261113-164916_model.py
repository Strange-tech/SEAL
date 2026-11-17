from __future__ import annotations

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Box,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    fit_to_box,
    mesh_from_cadquery,
)

# --------------------------------------------------------------------------
# Bookcase casework dimensions (metres, y-up / +z forward)
# --------------------------------------------------------------------------
W = 0.300          # overall width  (x)
D = 0.300          # overall depth  (z)
H = 1.980          # overall height (y)
T = 0.018          # board thickness
TB = 0.005         # back panel thickness

INNER_HALF = W / 2.0 - T          # 0.132 -> interior half width
SIDE_CX = W / 2.0 - T / 2.0       # 0.141 -> side panel centre x

# Adjustable-shelf support pins (drilled pin holes + shelf pins)
PIN_R = 0.003
PIN_LEN = 0.013
PIN_SEAT = 0.0005                 # pin crest sits just into the shelf underside
PIN_Z = (0.060, 0.240)            # pin columns along the depth

FIXED_SHELF_Y = (0.300, 0.960, 1.620)
ADJ_SHELF_Y = (0.630, 1.290)

FIXED_SHELF_D = 0.290
FIXED_SHELF_CZ = TB + FIXED_SHELF_D / 2.0     # 0.150

ADJ_SHELF_D = 0.288
ADJ_SHELF_CZ = 0.006 + ADJ_SHELF_D / 2.0      # 0.150
ADJ_SHELF_HALF_W = 0.130                       # 2 mm side clearance

# spare drilled pin-hole rows (heights where the shelves could be re-seated)
HOLE_Y = (
    0.420, 0.480, 0.540, 0.600, 0.690, 0.750,
    1.050, 1.110, 1.170, 1.230, 1.350, 1.410,
)
HOLE_R = 0.0025
HOLE_DEPTH = 0.006

SLIDE_TRAVEL = 0.030


def _side_panel_shape(sign: float) -> cq.Shape:
    """Side panel plate with shelf pins fused on and pin holes drilled.

    ``sign = +1`` builds the panel on +X (its pins point toward -X);
    ``sign = -1`` builds the panel on -X.  Geometry is authored in the panel
    local frame (plate centred on the origin).
    """
    body = cq.Solid.makeBox(T, H, D, cq.Vector(-T / 2.0, -H / 2.0, -D / 2.0))
    face_x = -sign * (T / 2.0)          # inner face x in the local frame

    def _axial(radius: float, length: float) -> cq.Shape:
        cyl = cq.Solid.makeCylinder(radius, length)
        return cyl.rotate((0, 0, 0), (0, 1, 0), -90.0 if sign > 0 else 90.0)

    # shelf pins for the two adjustable shelves
    for shelf_y in ADJ_SHELF_Y:
        pin_crest = shelf_y - T / 2.0 + PIN_SEAT
        ly = (pin_crest - PIN_R) - H / 2.0
        for pz in PIN_Z:
            pin = _axial(PIN_R, PIN_LEN).translate(
                (face_x + sign * 0.001, ly, pz - D / 2.0)
            )
            body = body.fuse(pin)

    # spare pin holes so the adjustable shelves can be re-seated
    for hy in HOLE_Y:
        for pz in PIN_Z:
            hole = _axial(HOLE_R, HOLE_DEPTH).translate(
                (face_x + sign * HOLE_DEPTH, hy - H / 2.0, pz - D / 2.0)
            )
            body = body.cut(hole)
    return body


def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="bookcase")

    oak = model.material("oak_veneer", rgba=(0.58, 0.42, 0.26, 1.0))
    hardboard = model.material("back_hardboard", rgba=(0.33, 0.26, 0.19, 1.0))

    # ---- root: bottom panel ------------------------------------------------
    bottom = model.part("bottom_panel")
    bottom.visual(
        Box((2 * INNER_HALF, T, D)),
        origin=Origin(xyz=(0.0, T / 2.0, D / 2.0)),
        material=oak,
        name="bottom_board",
    )

    # ---- side panels (load carrying uprights + shelf pins) -----------------
    for index, sign in enumerate((1.0, -1.0)):
        panel = model.part(f"side_panel_{index}")
        panel.visual(
            mesh_from_cadquery(
                _side_panel_shape(sign),
                f"side_panel_{index}",
                tolerance=0.0003,
            ),
            origin=Origin(),
            material=oak,
            name="side_board",
        )
        model.articulation(
            f"bottom_to_side_panel_{index}",
            ArticulationType.FIXED,
            parent=bottom,
            child=panel,
            origin=Origin(xyz=(sign * SIDE_CX, H / 2.0, D / 2.0)),
        )

    # ---- top panel ---------------------------------------------------------
    top = model.part("top_panel")
    top.visual(
        Box((2 * INNER_HALF, T, D)),
        material=oak,
        name="top_board",
    )
    model.articulation(
        "bottom_to_top_panel",
        ArticulationType.FIXED,
        parent=bottom,
        child=top,
        origin=Origin(xyz=(0.0, H - T / 2.0, D / 2.0)),
    )

    # ---- back panel --------------------------------------------------------
    back = model.part("back_panel")
    back.visual(
        Box((2 * INNER_HALF, H - 2 * T, TB)),
        material=hardboard,
        name="back_board",
    )
    model.articulation(
        "bottom_to_back_panel",
        ArticulationType.FIXED,
        parent=bottom,
        child=back,
        origin=Origin(xyz=(0.0, H / 2.0, TB / 2.0)),
    )

    # ---- fixed shelves -----------------------------------------------------
    for index, shelf_y in enumerate(FIXED_SHELF_Y):
        shelf = model.part(f"fixed_shelf_{index}")
        shelf.visual(
            Box((2 * INNER_HALF, T, FIXED_SHELF_D)),
            material=oak,
            name="shelf_board",
        )
        model.articulation(
            f"bottom_to_fixed_shelf_{index}",
            ArticulationType.FIXED,
            parent=bottom,
            child=shelf,
            origin=Origin(xyz=(0.0, shelf_y, FIXED_SHELF_CZ)),
        )

    # ---- adjustable shelves riding on the shelf pins -----------------------
    for index, shelf_y in enumerate(ADJ_SHELF_Y):
        shelf = model.part(f"adjustable_shelf_{index}")
        shelf.visual(
            Box((2 * ADJ_SHELF_HALF_W, T, ADJ_SHELF_D)),
            material=oak,
            name="shelf_board",
        )
        model.articulation(
            f"bottom_to_adjustable_shelf_{index}",
            ArticulationType.PRISMATIC,
            parent=bottom,
            child=shelf,
            origin=Origin(xyz=(0.0, shelf_y, ADJ_SHELF_CZ)),
            axis=(0.0, 1.0, 0.0),
            motion_limits=MotionLimits(
                effort=40.0,
                velocity=0.10,
                lower=0.0,
                upper=SLIDE_TRAVEL,
            ),
        )

    model = fit_to_box(model, (-1.84, 1.0, 0.3), (0.3, 2.0, 1.0))
    return model


def run_tests() -> TestReport:
    ctx = TestContext(object_model)

    bottom = object_model.get_part("bottom_panel")
    top = object_model.get_part("top_panel")
    back = object_model.get_part("back_panel")
    panel_0 = object_model.get_part("side_panel_0")
    panel_1 = object_model.get_part("side_panel_1")
    fixed_0 = object_model.get_part("fixed_shelf_0")
    fixed_2 = object_model.get_part("fixed_shelf_2")
    adj_0 = object_model.get_part("adjustable_shelf_0")
    adj_joint = object_model.get_articulation("bottom_to_adjustable_shelf_0")

    # overall casework proportions
    ctx.expect_gap(
        top, bottom, axis="y", min_gap=1.90, max_gap=1.99,
        name="casework is a tall bookcase",
    )
    ctx.expect_gap(
        panel_0, panel_1, axis="x", min_gap=0.260, max_gap=0.270,
        name="interior width between the uprights",
    )

    # support: every board really touches the casework
    ctx.expect_contact(panel_0, bottom, contact_tol=1e-4, name="upright seated on bottom")
    ctx.expect_contact(panel_1, bottom, contact_tol=1e-4, name="second upright seated on bottom")
    ctx.expect_contact(top, panel_0, contact_tol=1e-4, name="top panel caps the upright")
    ctx.expect_contact(back, bottom, contact_tol=1e-4, name="back panel rests on the bottom")
    ctx.expect_contact(fixed_0, panel_0, contact_tol=1e-4, name="fixed shelf meets upright")
    ctx.expect_contact(fixed_2, back, contact_tol=1e-4, name="fixed shelf meets the back")

    # the back panel closes the rear, shelves stop behind the front edge
    ctx.expect_gap(
        fixed_0, back, axis="z", min_gap=-0.0005, max_gap=0.001,
        name="shelf butts against the back panel",
    )
    ctx.expect_gap(
        panel_0, fixed_0, axis="z", min_gap=0.001, max_gap=0.010,
        name="shelves are recessed behind the front edge",
    )

    # adjustable shelf: clear of the uprights, carried by the shelf pins
    ctx.expect_gap(
        panel_0, adj_0, axis="x", min_gap=0.001, max_gap=0.004,
        name="adjustable shelf clears the +x upright",
    )
    ctx.expect_gap(
        adj_0, panel_1, axis="x", min_gap=0.001, max_gap=0.004,
        name="adjustable shelf clears the -x upright",
    )
    ctx.expect_contact(
        adj_0, panel_0, contact_tol=0.001, name="adjustable shelf sits on the pins",
    )
    ctx.expect_contact(
        adj_0, panel_1, contact_tol=0.001, name="adjustable shelf sits on both pin sets",
    )

    # the shelf can be lifted off its pins and re-seated
    rest_pos = ctx.part_world_position(adj_0)
    with ctx.pose({adj_joint: SLIDE_TRAVEL}):
        lifted_pos = ctx.part_world_position(adj_0)
        ctx.expect_gap(
            fixed_2, adj_0, axis="y", min_gap=0.05,
            name="lifted shelf still clears the shelf above",
        )
    ctx.check(
        "adjustable shelf lifts off its pins",
        rest_pos is not None
        and lifted_pos is not None
        and lifted_pos[1] > rest_pos[1] + 0.02,
        details=f"rest={rest_pos}, lifted={lifted_pos}",
    )

    return ctx.report()


object_model = build_object_model()

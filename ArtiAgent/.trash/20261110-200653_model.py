"""Nintendo DS Lite style dual-screen clamshell handheld console.

Authored in real-world metres.  Object frame:
    +X = width (viewer's right when facing the screens is +X? -> viewer's LEFT is -X)
    -Y = front edge (where the stylus / audio jack live)
    +Y = back edge (hinge barrel)
    +Z = up out of the lower body's top face.

Root part: ``lower_body`` (fixed base slab, z in [0, 0.022]).
Child part: ``upper_lid`` (same 133 x 74 footprint, hinged at the rear edge).

The lid mesh is authored in its *closed* pose inside the lid part frame, and the
articulation frame is pre-rotated by -130 deg about the hinge axis, so the
model's rest pose (q = 0) is the open, in-use pose requested by the artwork.
Rotating q towards the lower limit folds the lid shut.
"""

from __future__ import annotations

import math

import cadquery as cq

from sdk import (
    ArticulatedObject,
    ArticulationType,
    Cylinder,
    Material,
    MotionLimits,
    Origin,
    TestContext,
    TestReport,
    mesh_from_cadquery,
)

# ----------------------------------------------------------------- footprint
W = 0.133          # width  (X)
D = 0.074          # depth  (Y)
H = 0.022          # thickness of each half (Z)

CORNER_R = 0.006
TOP_FILLET = 0.0025
BOT_FILLET = 0.0015

# hinge barrel
HY = 0.037         # hinge axis y (rear edge of the lower body)
HZ = 0.022         # hinge axis z (bottom of the barrel at the top/rear edge)
BARREL_R = 0.004
CRADLE_R = 0.0038  # base cradle the lid knuckle seats into (0.2 mm bite)
CAP_X0, CAP_X1 = 0.0450, 0.0640   # base barrel end caps
KNUCK_HALF = 0.0440               # lid centre knuckle half length

OPEN_DEG = 130.0
OPEN_RAD = math.radians(OPEN_DEG)

# lower face layout
SCREEN_Y = 0.0015
SCREEN_W, SCREEN_D = 0.062, 0.046
BEZEL_W, BEZEL_D = 0.0664, 0.0504
SURR_W, SURR_D = 0.0696, 0.0536
POCKET_W, POCKET_D = 0.0700, 0.0540

DPAD = (-0.0490, 0.0020)
FACE_C = (0.0470, 0.0020)
FACE_BUTTONS = (
    ("button_y", (0.0470, 0.0130)),
    ("button_x", (0.0580, 0.0020)),
    ("button_a", (0.0360, 0.0020)),
    ("button_b", (0.0470, -0.0090)),
)
AUX_BUTTONS = (("start_button", (0.0430, -0.0285)), ("select_button", (0.0330, -0.0285)))

MIC = (0.0, -0.0330)
VOL = (-0.0030, 0.0065)      # y, z on the left side face
VOL_LEN, VOL_H = 0.018, 0.006
SD = (0.0180, 0.0040)
SD_LEN, SD_H = 0.016, 0.003
STYLUS = (-0.0330, 0.0050)   # x, z on the front face
STYLUS_LEN, STYLUS_H = 0.038, 0.003
JACK = (0.0450, 0.0065)      # x, z on the front face

# lid face layout
LID_YC = -0.039
SPEAKER_CX = 0.0475
SPEAKER_DOT_R = 0.0010


# ------------------------------------------------------------------ helpers
def rounded_prism(w, d, h, r, *, center=(0.0, 0.0), z0=0.0):
    sk = cq.Sketch().rect(w, d).vertices().fillet(r)
    return (
        cq.Workplane("XY")
        .workplane(offset=z0)
        .center(center[0], center[1])
        .placeSketch(sk)
        .extrude(h)
    )


def rect_prism(w, d, h, *, center=(0.0, 0.0), z0=0.0):
    return (
        cq.Workplane("XY")
        .workplane(offset=z0)
        .center(center[0], center[1])
        .rect(w, d)
        .extrude(h)
    )


def x_cyl(y, z, x0, x1, r):
    """Cylinder along +X starting at x0."""
    return cq.Workplane("YZ").workplane(offset=x0).center(y, z).circle(r).extrude(x1 - x0)


def z_cyl(x, y, z0, z1, r):
    """Cylinder along +Z starting at z0."""
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)


def y_cyl(x, z, y0, y1, r):
    """Cylinder along +Y starting at y0 (front-edge bores)."""
    return cq.Workplane("ZX").workplane(offset=y0).center(z, x).circle(r).extrude(y1 - y0)


def x_prism(yc, zc, dy, dz, x0, dx, r=None):
    """Rectangular / rounded prism extruded along +X (side-face slots)."""
    if r:
        sk = cq.Sketch().rect(dy, dz).vertices().fillet(r)
        return (
            cq.Workplane("YZ")
            .workplane(offset=x0)
            .center(yc, zc)
            .placeSketch(sk)
            .extrude(dx)
        )
    return cq.Workplane("YZ").workplane(offset=x0).center(yc, zc).rect(dy, dz).extrude(dx)


def y_prism(xc, zc, dx, dz, y0, dy):
    """Rectangular prism extruded along +Y (front-edge slots)."""
    return cq.Workplane("ZX").workplane(offset=y0).center(zc, xc).rect(dz, dx).extrude(dy)


def cq_mesh(shape, name):
    return mesh_from_cadquery(shape, name, tolerance=0.0003, angular_tolerance=0.08)


# ------------------------------------------------------------- lower body
def _lower_body_shell():
    body = rounded_prism(W, D, H, CORNER_R)
    body = body.faces(">Z").edges().fillet(TOP_FILLET)
    body = body.faces("<Z").edges().fillet(BOT_FILLET)

    # rear hinge barrel: two end caps belong to the base, a cradle is cut at the
    # centre where the lid's own knuckle seats.
    body = body.union(x_cyl(HY, HZ, CAP_X0, CAP_X1, BARREL_R))
    body = body.union(x_cyl(HY, HZ, -CAP_X1, -CAP_X0, BARREL_R))
    body = body.cut(x_cyl(HY, HZ, -0.0445, 0.0445, CRADLE_R))

    # recessed screen pocket on the top face
    body = body.cut(
        rounded_prism(POCKET_W, POCKET_D, 0.0025, 0.0040, center=(0.0, SCREEN_Y), z0=0.0207)
    )
    # D-pad dish
    body = body.cut(z_cyl(DPAD[0], DPAD[1], 0.0214, 0.0222, 0.0105))
    # face-button cups
    for _name, (bx, by) in FACE_BUTTONS:
        body = body.cut(z_cyl(bx, by, 0.0216, 0.0222, 0.0039))
    # microphone bore
    body = body.cut(z_cyl(MIC[0], MIC[1], 0.0212, 0.0222, 0.00125))
    # left side: volume slider recess + SD card slot
    body = body.cut(
        x_prism(VOL[0], VOL[1], VOL_LEN, VOL_H, -0.0665, 0.0009, r=0.0012)
    )
    body = body.cut(x_prism(SD[0], SD[1], SD_LEN, SD_H, -0.0665, 0.0010, r=0.0008))
    # front edge: stylus slot + audio jack
    body = body.cut(
        y_prism(STYLUS[0], STYLUS[1], STYLUS_LEN, STYLUS_H, -0.037, 0.0032)
    )
    body = body.cut(y_cyl(JACK[0], JACK[1], -0.037, -0.0322, 0.0018))
    return body


def build_lower_body(model, mats):
    lower = model.part("lower_body")
    lower.visual(mats["shell"], name="noop") if False else None
    lower.visual(cq_mesh(_lower_body_shell(), "lower_body_shell"))

    # thin light-grey seam frame around the display
    lower.visual(
        cq_mesh(
            rounded_prism(0.0696, 0.0536, 0.0016, 0.0035, center=(0.0, SCREEN_Y), z0=0.0205),
            "lower_bezel_surround",
        )
    )
    # glossy near-black bezel with a shallow glass pocket
    bezel = rounded_prism(0.0664, 0.0504, 0.0015, 0.0032, center=(0.0, SCREEN_Y), z0=0.0211)
    bezel = bezel.cut(
        rounded_prism(0.0628, 0.0468, 0.0007, 0.0030, center=(0.0, SCREEN_Y), z0=0.0221)
    )
    lower.visual(cq_mesh(bezel, "lower_bezel"))
    # dark glass panel seated in the bezel
    lower.visual(
        cq_mesh(
            rounded_prism(SCREEN_W, SCREEN_D, 0.0007, 0.0028, center=(0.0, SCREEN_Y), z0=0.0217),
            "lower_screen_glass",
        )
    )

    # D-pad cross
    dpad = rounded_prism(0.016, 0.005, 0.0020, 0.0015, center=DPAD, z0=0.0212)
    dpad = dpad.union(rounded_prism(0.005, 0.016, 0.0020, 0.0015, center=DPAD, z0=0.0212))
    lower.visual(cq_mesh(dpad, "dpad"))

    # four round face buttons in a diamond
    for name, (bx, by) in FACE_BUTTONS:
        btn = z_cyl(bx, by, 0.0214, 0.0230, 0.0036)
        btn = btn.faces(">Z").edges().fillet(0.0007)
        lower.visual(cq_mesh(btn, name))

    # START / SELECT ovals
    for name, (sx, sy) in AUX_BUTTONS:
        lower.visual(
            cq_mesh(
                rounded_prism(0.0070, 0.0032, 0.0014, 0.0014, center=(sx, sy), z0=0.0214),
                name,
            )
        )

    # microphone aperture (dark disc inside the bore)
    lower.visual(
        Cylinder(radius=0.0013, length=0.0007),
        origin=Origin(xyz=(MIC[0], MIC[1], 0.02125)),
        name="mic_aperture",
    )

    # left side volume slider knob (seated in its slot)
    lower.visual(
        cq_mesh(
            x_prism(VOL[0] - 0.0060, VOL[1], 0.0080, 0.0040, -0.0685, 0.0035, r=0.0008),
            "volume_slider",
        )
    )
    # SD card slot liner (dark)
    lower.visual(
        cq_mesh(
            x_prism(SD[0], SD[1], 0.0154, 0.0026, -0.0663, 0.0016, r=0.0006),
            "sd_slot",
        )
    )
    # stylus slot liner (dark)
    lower.visual(
        cq_mesh(
            y_prism(STYLUS[0], STYLUS[1], 0.0370, 0.0026, -0.0368, 0.0023),
            "stylus_slot",
        )
    )
    # audio jack barrel (dark)
    lower.visual(
        cq_mesh(y_cyl(JACK[0], JACK[1], -0.0368, -0.0325, 0.00185), "audio_jack")
    )
    return lower


# --------------------------------------------------------------- upper lid
def _lid_shell():
    body = rounded_prism(W, 0.070, H, CORNER_R, center=(0.0, LID_YC), z0=0.0)
    body = body.faces(">Z").edges().fillet(TOP_FILLET)
    body = body.faces("<Z").edges().fillet(BOT_FILLET)

    # hinge boss: centre knuckle on the barrel axis + leaf tying it to the shell
    knuckle = x_cyl(0.0, 0.0, -KNUCK_HALF, KNUCK_HALF, BARREL_R)
    leaf = rect_prism(2 * KNUCK_HALF, 0.0055, 0.0025, center=(0.0, -0.00225), z0=0.0)
    body = body.union(knuckle).union(leaf)

    # inner-face display pocket
    body = body.cut(
        rounded_prism(POCKET_W, POCKET_D, 0.0025, 0.0040, center=(0.0, LID_YC), z0=-0.0012)
    )
    # stereo speaker perforations (6 dots per side)
    for sx, sy in _speaker_holes():
        body = body.cut(z_cyl(sx, sy, -0.0010, 0.0016, SPEAKER_DOT_R))
    return body


def _speaker_holes():
    holes = []
    for side in (-1.0, 1.0):
        for col in (-0.0035, 0.0035):
            for row in (-0.0035, 0.0, 0.0035):
                holes.append((side * SPEAKER_CX + col, LID_YC + row))
    return holes


def build_upper_lid(model, mats):
    lid = model.part("upper_lid")
    lid.visual(cq_mesh(_lid_shell(), "upper_lid_shell"))

    # seam frame + glossy bezel + glass on the inner face (local z = 0 side)
    lid.visual(
        cq_mesh(
            rounded_prism(0.0696, 0.0536, 0.0016, 0.0035, center=(0.0, LID_YC), z0=-0.0001),
            "upper_bezel_surround",
        )
    )
    bezel = rounded_prism(0.0664, 0.0504, 0.0015, 0.0032, center=(0.0, LID_YC), z0=-0.0006)
    bezel = bezel.cut(
        rounded_prism(0.0628, 0.0468, 0.0007, 0.0030, center=(0.0, LID_YC), z0=-0.0016)
    )
    lid.visual(cq_mesh(bezel, "upper_bezel"))
    lid.visual(
        cq_mesh(
            rounded_prism(SCREEN_W, SCREEN_D, 0.0007, 0.0028, center=(0.0, LID_YC), z0=-0.0003),
            "upper_screen_glass",
        )
    )

    # dark seats behind each speaker perforation
    for i, (sx, sy) in enumerate(_speaker_holes()):
        lid.visual(
            Cylinder(radius=0.00105, length=0.0006),
            origin=Origin(xyz=(sx, sy, 0.00145)),
            name=f"speaker_dot_{i}",
        )
    return lid


# ----------------------------------------------------------------- assembly
def build_object_model() -> ArticulatedObject:
    model = ArticulatedObject(name="ds_lite_dual_screen_console")

    mats = {
        "shell": model.material(name="matte_charcoal", rgba=(0.076, 0.077, 0.086)),
        "bezel": model.material(name="gloss_black", rgba=(0.022, 0.022, 0.027)),
        "glass": model.material(name="screen_glass", rgba=(0.048, 0.058, 0.078)),
        "seam": model.material(name="panel_seam", rgba=(0.60, 0.61, 0.63)),
        "button": model.material(name="button_dark", rgba=(0.15, 0.15, 0.16)),
        "hole": model.material(name="aperture_black", rgba=(0.008, 0.008, 0.010)),
        "slider": model.material(name="slider_grey", rgba=(0.24, 0.24, 0.25)),
    }

    lower = build_lower_body(model, mats)
    lid = build_upper_lid(model, mats)

    # material assignment (visuals are created plain, then tinted by name)
    _tint(lower, mats)
    _tint(lid, mats)

    model.articulation(
        "body_to_lid",
        ArticulationType.REVOLUTE,
        parent=lower,
        child=lid,
        # Articulation frame sits on the barrel axis and is pre-rotated so the
        # rest pose (q = 0) shows the lid open at 130 degrees.
        origin=Origin(xyz=(0.0, HY, HZ), rpy=(-OPEN_RAD, 0.0, 0.0)),
        axis=(-1.0, 0.0, 0.0),
        motion_limits=MotionLimits(
            effort=2.5, velocity=3.0, lower=-OPEN_RAD, upper=0.0
        ),
    )
    return model


def _tint(part, mats):
    """Assign the intended material to each named visual of a body."""
    mapping = {
        "shell": mats["shell"],
        "bezel_surround": mats["seam"],
        "bezel": mats["bezel"],
        "screen_glass": mats["glass"],
        "dpad": mats["button"],
        "button_y": mats["button"],
        "button_x": mats["button"],
        "button_a": mats["button"],
        "button_b": mats["button"],
        "start_button": mats["button"],
        "select_button": mats["button"],
        "mic_aperture": mats["hole"],
        "volume_slider": mats["slider"],
        "sd_slot": mats["hole"],
        "stylus_slot": mats["hole"],
        "audio_jack": mats["hole"],
    }
    for visual in part.visuals:
        name = visual.name or ""
        key = name.replace("lower_", "").replace("upper_", "").replace("_shell", "shell")
        if name.endswith("_shell"):
            key = "shell"
        mat = mapping.get(key) or mapping.get(name)
        if mat is None and name.startswith("speaker_dot"):
            mat = mats["hole"]
        if mat is not None:
            visual.material = mat


# -------------------------------------------------------------------- tests
def run_tests() -> TestReport:
    ctx = TestContext(object_model)
    base = object_model.get_part("lower_body")
    lid = object_model.get_part("upper_lid")
    hinge = object_model.get_articulation("body_to_lid")
    limits = hinge.motion_limits

    ctx.check(
        "single fixed root",
        [p.name for p in object_model.root_parts()] == ["lower_body"],
        details=str([p.name for p in object_model.root_parts()]),
    )
    ctx.check(
        "lid hinge is revolute",
        hinge.articulation_type == ArticulationType.REVOLUTE,
        details=str(hinge.articulation_type),
    )
    ctx.check(
        "hinge travel is 130 degrees",
        limits is not None and abs((limits.upper - limits.lower) - OPEN_RAD) < 1e-9,
        details=str(limits),
    )
    ctx.check(
        "hinge axis runs along the width",
        abs(hinge.axis[0]) > 0.99 and abs(hinge.axis[1]) < 1e-9 and abs(hinge.axis[2]) < 1e-9,
        details=str(hinge.axis),
    )

    # rest pose must be the open, in-use pose
    open_box = ctx.part_world_aabb(lid)
    ctx.check(
        "lid rests open at 130 degrees",
        open_box is not None and open_box[1][2] > 0.070 and open_box[1][1] > 0.090,
        details=str(open_box),
    )

    # hinge support: the lid's centre knuckle bites 0.2 mm into the base cradle
    ctx.expect_contact(
        lid, base, contact_tol=1e-5, name="lid knuckle bears in the base hinge cradle"
    )

    base_box = ctx.part_world_aabb(base)
    with ctx.pose({hinge: limits.lower}):
        closed_box = ctx.part_world_aabb(lid)
        ctx.check(
            "closed lid folds onto the lower body",
            closed_box is not None
            and base_box is not None
            and abs(closed_box[1][2] - (base_box[1][2] + 0.018)) < 0.004,
            details=f"closed={closed_box}, base={base_box}",
        )
        ctx.expect_within(
            lid, base, axes="xy", margin=0.002, name="closed lid matches the base footprint"
        )
        ctx.expect_contact(
            lid, base, contact_tol=1e-5, name="closed lid still held by the hinge"
        )

    base_names = {v.name for v in base.visuals}
    ctx.check(
        "lower controls and screen are present",
        {
            "dpad",
            "button_a",
            "button_x",
            "button_y",
            "button_b",
            "start_button",
            "select_button",
            "lower_screen_glass",
            "volume_slider",
            "sd_slot",
            "stylus_slot",
            "audio_jack",
        }
        <= base_names,
        details=str(sorted(base_names)),
    )
    lid_names = {v.name for v in lid.visuals}
    ctx.check(
        "lid screen and stereo speaker grilles are present",
        {"upper_screen_glass"} <= lid_names
        and len([n for n in lid_names if n.startswith("speaker_dot")]) == 12,
        details=str(sorted(lid_names)),
    )

    return ctx.report()


object_model = build_object_model()

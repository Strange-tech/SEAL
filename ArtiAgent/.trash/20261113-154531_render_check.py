"""Pure-python OBJ z-buffer ASCII renderer used only for eyeballing the model."""
import math
import os
import sys

MESH_DIR = ".compile_tmp/assets/meshes"

OFF = {
    "lower_housing_shell": (0.0, 0.0, 0.0),
    "lower_bezel": (0.0, 0.0, 0.0),
    "lower_lcd": (0.0, 0.0, 0.0),
    "lid_shell": (0.0, 0.037, 0.0118),
    "upper_bezel": (0.0, 0.037, 0.0118),
    "upper_lcd": (0.0, 0.037, 0.0118),
    "dpad_hub": (-0.0445, 0.0, 0.0085),
    "dpad_cross": (-0.0445, 0.0, 0.0104),
    "face_button_x_cap": (0.0415, 0.0102, 0.011),
    "face_button_y_cap": (0.0313, 0.0, 0.011),
    "face_button_a_cap": (0.0517, 0.0, 0.011),
    "face_button_b_cap": (0.0415, -0.0102, 0.011),
    "pill_button_select_cap": (-0.03, -0.0295, 0.011),
    "pill_button_start_cap": (0.03, -0.0295, 0.011),
    "power_slider": (0.0651, -0.020, 0.0073),
    "volume_slider": (-0.0651, -0.010, 0.0083),
    "shoulder_left_lever": (-0.0515, 0.0300, 0.0040),
    "shoulder_right_lever": (0.0515, 0.0300, 0.0040),
    "stylus": (0.0648, -0.013, 0.0073),
    "game_pak": (0.0, 0.004, 0.0039),
    "gba_cart": (0.0, -0.012, 0.0034),
    "battery_cover": (0.0, 0.019, 0.0),
}


def load(name):
    path = os.path.join(MESH_DIR, name + ".obj")
    vs, fs = [], []
    with open(path, "r") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                vs.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
                for i in range(1, len(idx) - 1):
                    fs.append((idx[0], idx[i], idx[i + 1]))
    off = OFF.get(name, (0.0, 0.0, 0.0))
    vs = [(v[0] + off[0], v[1] + off[1], v[2] + off[2]) for v in vs]
    return vs, fs


def render(tris, uax, vax, dax, cols, rows, flip_u=False, flip_v=False, title=""):
    us = [t[0][uax] for t in tris] + [t[1][uax] for t in tris] + [t[2][uax] for t in tris]
    vs_ = [t[0][vax] for t in tris] + [t[1][vax] for t in tris] + [t[2][vax] for t in tris]
    u0, u1, v0, v1 = min(us), max(us), min(vs_), max(vs_)
    su = (u1 - u0) or 1e-6
    sv = (v1 - v0) or 1e-6
    scale = min((cols - 1) / su, (rows - 1) / sv * 0.5)
    zbuf = [[-1e9] * cols for _ in range(rows)]
    cbuf = [[" "] * cols for _ in range(rows)]
    ramp = " .:-=+*#%@"
    for tri in tris:
        pts = []
        for v in tri:
            cu = (v[uax] - u0) * scale
            cv = (v[vax] - v0) * scale * 2.0
            if flip_u:
                cu = (cols - 1) - cu
            if flip_v:
                cv = (rows - 1) - cv
            pts.append((cu, cv, v[dax]))
        e1 = [tri[1][i] - tri[0][i] for i in range(3)]
        e2 = [tri[2][i] - tri[0][i] for i in range(3)]
        nx = e1[1] * e2[2] - e1[2] * e2[1]
        ny = e1[2] * e2[0] - e1[0] * e2[2]
        nz = e1[0] * e2[1] - e1[1] * e2[0]
        nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        shade = abs(nz) / nl * 0.75 + 0.25
        ch = ramp[min(len(ramp) - 1, int(shade * (len(ramp) - 1)))]
        (x0_, y0_, d0), (x1_, y1_, d1), (x2_, y2_, d2) = pts
        minx = max(0, int(min(x0_, x1_, x2_)))
        maxx = min(cols - 1, int(max(x0_, x1_, x2_)) + 1)
        miny = max(0, int(min(y0_, y1_, y2_)))
        maxy = min(rows - 1, int(max(y0_, y1_, y2_)) + 1)
        det = (y1_ - y2_) * (x0_ - x2_) + (x2_ - x1_) * (y0_ - y2_)
        if abs(det) < 1e-12:
            continue
        for py in range(miny, maxy + 1):
            for px in range(minx, maxx + 1):
                l0 = ((y1_ - y2_) * (px - x2_) + (x2_ - x1_) * (py - y2_)) / det
                l1 = ((y2_ - y0_) * (px - x2_) + (x0_ - x2_) * (py - y2_)) / det
                l2 = 1.0 - l0 - l1
                if l0 < -0.02 or l1 < -0.02 or l2 < -0.02:
                    continue
                d = l0 * d0 + l1 * d1 + l2 * d2
                if d > zbuf[py][px]:
                    zbuf[py][px] = d
                    cbuf[py][px] = ch
    print("=== " + title)
    for row in cbuf:
        print("".join(row))


names = sorted(n[:-4] for n in os.listdir(MESH_DIR) if n.endswith(".obj") and n[:-4] in OFF)
tris = []
for n in names:
    vs, fs = load(n)
    for f in fs:
        tris.append((vs[f[0]], vs[f[1]], vs[f[2]]))
print("meshes:", len(names), "tris:", len(tris))
render(tris, 0, 1, 2, 118, 44, title="TOP view (x right, y up/back, depth z)")
render(tris, 0, 2, -1, 118, 40, title="FRONT view (x right, z up, depth -y)")
render(tris, 1, 2, 0, 60, 34, title="SIDE view (y, z, depth x)")

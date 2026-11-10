"""Manhattan-world regularization: East/North orthogonal basis estimation + orientation snap (pure NumPy).

Corresponds to plan.md tool 3 "build a custom East/North basis and Project the scene onto the custom basis". Wall orientations (yaw) are equivalent modulo 90deg, so a 4-theta circular mean estimates the grid orientation, then wall/object/door/window theta[1] is snapped to the nearest grid direction.
"""

import numpy as np


def estimate_grid_orientation(yaws_deg):
    """Estimate the Manhattan grid orientation (in [0, 90)) from a set of yaw angles (degrees).

    Uses a 4-theta circular mean: wall orientations are equivalent modulo 90deg, so take the mean of 4-theta and divide by 4.
    Returns the grid base angle (East direction); North = East + 90deg.
    """
    yaws = np.asarray(yaws_deg, dtype=float)
    if yaws.size == 0:
        return 0.0
    four = np.radians(4.0 * yaws)
    mean_vec = np.array([np.cos(four).mean(), np.sin(four).mean()])
    if np.linalg.norm(mean_vec) < 1e-9:
        return 0.0
    grid = round(np.degrees(np.arctan2(mean_vec[1], mean_vec[0])) / 4.0, 9) % 90.0
    return float(grid)


def snap_yaw_to_basis(yaw_deg, basis_deg=0.0, angle_threshold=15.0):
    """Snap yaw to the orthogonal basis {basis, basis+90, basis+180, basis+270}.

    If the angle to the nearest grid direction exceeds angle_threshold, keep the original value (do not force-straighten).
    """
    yaw = float(yaw_deg)
    b = float(basis_deg) % 90.0
    grid = np.array([b, b + 90.0, b + 180.0, b + 270.0])
    diff = (yaw - grid + 90.0) % 180.0 - 90.0  # minimum signed angle to each grid line ([-90,90])
    i = int(np.argmin(np.abs(diff)))
    if abs(diff[i]) <= angle_threshold:
        return float(grid[i] % 360.0)
    return yaw


def manhattan_regularize_nodes(nodes, angle_threshold=15.0):
    """Manhattan-regularize the scene graph nodes, returning a new node list (the originals are not mutated).

    - estimate the grid orientation from wall yaws (or all non-floor nodes if there are no walls).
    - snap wall/object/door/window theta[1] to the orthogonal basis.
    - floor (horizontal surface) is left untouched.
    """
    wall_yaws = [n["theta"][1] for n in nodes if n["type"] == "wall"]
    if not wall_yaws:
        wall_yaws = [n["theta"][1] for n in nodes if n["type"] != "floor"]
    basis = estimate_grid_orientation(wall_yaws)

    out = []
    for n in nodes:
        if n["type"] == "floor":
            out.append(n)
            continue
        theta = list(n["theta"])
        theta[1] = snap_yaw_to_basis(n["theta"][1], basis, angle_threshold)
        out.append({**n, "theta": theta})
    return out

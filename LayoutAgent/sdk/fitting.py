"""OBB fitting and plane detection (pure NumPy).

Corresponds to plan.md step 5 "OBB (center/position/scale)" and step 5.5 "estimate dominant directions from detected wall/floor OBBs". Indoor objects/walls/floors are "upright" (roll=pitch=0), so the main fitter ``upright_obb`` only does PCA on the horizontal (xz) plane to estimate yaw, and takes height from the y range.
"""

import numpy as np

from .projection import unproject_masked


def upright_obb(points, min_extent=0.01):
    """Fit a point cloud to an "upright" OBB: roll=pitch=0, only yaw estimated.

    Returns ``(center, dims, theta)``, dims = [width (principal), height, length], theta = [0, yaw, 0].
    yaw aligns the local x axis (dims[0]) with the horizontal principal direction.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 4 or pts.shape[1] != 3:
        return None

    xz = pts[:, [0, 2]]
    c2 = xz.mean(axis=0)
    cov = (xz - c2).T @ (xz - c2) / xz.shape[0]
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending
    u = eigvecs[:, 1]                      # principal direction (in the xz plane, 2D)
    # local x = Ry(yaw) e_x = (cos yaw, -sin yaw); set it = u -> yaw = atan2(-u_z, u_x)
    yaw = float(np.degrees(np.arctan2(-u[1], u[0])))
    v = np.array([-u[1], u[0]])            # perpendicular direction

    proj_u = (xz - c2) @ u
    proj_v = (xz - c2) @ v
    du = max(float(proj_u.max() - proj_u.min()), min_extent)
    dv = max(float(proj_v.max() - proj_v.min()), min_extent)

    ymin, ymax = float(pts[:, 1].min()), float(pts[:, 1].max())
    height = max(ymax - ymin, min_extent)
    cy = (ymin + ymax) / 2.0

    center_xz = c2 + u * ((proj_u.min() + proj_u.max()) / 2.0) + v * ((proj_v.min() + proj_v.max()) / 2.0)
    center = [float(center_xz[0]), cy, float(center_xz[1])]
    return center, [du, height, dv], [0.0, yaw, 0.0]


def mask_to_obb(depth, intrinsics, extrinsics, mask, min_points=50):
    """mask -> backprojected point cloud -> upright OBB. Returns None if too few points."""
    pts = unproject_masked(depth, intrinsics, extrinsics, mask)
    if pts.shape[0] < min_points:
        return None
    return upright_obb(pts)


def fit_plane_ransac(points, distance_threshold=0.02, max_iterations=300,
                     min_inliers_ratio=0.2, seed=0):
    """RANSAC plane fit. Returns ``(normal, d, inlier_mask)`` satisfying ``normal·p = d``.

    The normal is corrected to point up (normal[1] >= 0). Returns None if not found.
    """
    rng = np.random.default_rng(seed)
    pts = np.asarray(points, dtype=float)
    n = pts.shape[0]
    if n < 3:
        return None

    best = None
    for _ in range(max_iterations):
        idx = rng.choice(n, 3, replace=False)
        p0, p1, p2 = pts[idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:
            continue
        normal = normal / norm
        d = float(normal @ p0)
        inliers = np.abs(pts @ normal - d) < distance_threshold
        count = int(inliers.sum())
        if count >= n * min_inliers_ratio and (best is None or count > best[0]):
            best = (count, normal, d, inliers)

    if best is None:
        return None
    _, normal, d, inliers = best

    # refit with inliers (least squares: the smallest-singular-value direction is the normal)
    in_pts = pts[inliers]
    c = in_pts.mean(axis=0)
    _, _, vh = np.linalg.svd(in_pts - c, full_matrices=False)
    normal = vh[-1]
    if normal[1] < 0:
        normal = -normal
    d = float(normal @ c)
    return normal, d, inliers


def detect_floor(points, distance_threshold=0.02, thickness=0.1, seed=0):
    """Detect the floor: fit a near-horizontal plane and return its upright OBB (fixed thickness).

    Returns ``(center, dims, theta)`` or None.
    """
    res = fit_plane_ransac(points, distance_threshold=distance_threshold, seed=seed)
    if res is None:
        return None
    normal, d, inliers = res
    if abs(normal[1]) < 0.7:  # not a horizontal plane
        return None
    pts = np.asarray(points, dtype=float)[inliers]
    obb = upright_obb(pts)
    if obb is None:
        return None
    center, dims, theta = obb
    # floor: thickness is vertical, put the center at the plane height
    center = [center[0], float(d) - thickness / 2.0, center[2]]
    dims = [dims[0], thickness, dims[2]]
    return center, dims, [0.0, theta[1], 0.0]


def detect_walls(points, distance_threshold=0.02, min_wall_points=200,
                 thickness=0.16, seed=0):
    """Greedily detect vertical wall planes: repeatedly RANSAC-fit vertical planes, removing inliers each time.

    Returns a list of wall OBBs ``[(center, dims, theta), ...]``.
    """
    rng = np.random.default_rng(seed)
    remaining = np.asarray(points, dtype=float)
    walls = []
    while remaining.shape[0] >= min_wall_points:
        res = fit_plane_ransac(remaining, distance_threshold=distance_threshold,
                               seed=int(rng.integers(0, 2 ** 31)))
        if res is None:
            break
        normal, d, inliers = res
        if abs(normal[1]) > 0.5:  # not a vertical plane; stop (floor/ceiling already excluded or absent)
            break
        count = int(inliers.sum())
        if count < min_wall_points:
            break
        wall_pts = remaining[inliers]
        obb = upright_obb(wall_pts)
        if obb is not None:
            center, dims, theta = obb
            # wall: thickness along the horizontal normal, correct the center with the plane offset
            # simplification: keep the upright_obb result, just use the min value for thickness
            walls.append((center, [dims[0], dims[1], thickness], [0.0, theta[1], 0.0]))
        remaining = remaining[~inliers]
    return walls

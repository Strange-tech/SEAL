"""Rigid alignment from the room frame (y-up) to the DA3 world frame (camera frame), in pure NumPy.

Single-frame DA3's world frame is approximately the camera frame (extrinsics ~ identity, x right / y down / z forward, camera at origin).
But room.py uses a y-up room frame (the reference horizontal surface — floor or countertop — has its top at y~0, the back wall at z~0, +z toward the viewer).
This module estimates the w2c rigid transform ``[R|t]`` (3x4, ``cam = R @ room + t``) that maps the room frame into the camera frame, used by compile's image reprojection validation.

room.py is "image-anchored": +x = image right (= camera x projected onto the horizontal plane), +y up, +z toward the camera. Therefore yaw is always 0, and only up (pitch/roll), depth, and x-offset need to be estimated:
- reference horizontal surface (floor/countertop) normal -> up (pitch/roll) and camera height above the surface;
- if there is a confident back wall (roughly facing the camera and the farthest vertical plane along that normal), it fixes yaw/depth directly — a fallback for rooms that are themselves yawed; in close-ups a slanted cabinet front or an occluded back wall is rejected;
- depth otherwise takes the 98th percentile of the whole point cloud along forward (capturing the back wall rather than the foreground cabinet front);
- x-offset takes the lateral component of the reference surface centroid.
"""

import numpy as np

from .projection import unproject_masked
from .fitting import fit_plane_ransac

# RANSAC plane fitting only needs a few tens of thousands of points to find the
# dominant planes. DA3 now runs at process_res=1008 (~200k points); subsample
# back to the ~50k that 504 px produced so alignment stays fast without changing
# the depth map used for backprojection.
_RANSAC_MAX_POINTS = 50_000
_RANSAC_SEED = 0


def _subsample(points, max_points, seed=_RANSAC_SEED):
    """Deterministically subsample a point cloud to at most ``max_points`` rows."""
    points = np.asarray(points, dtype=float)
    n = points.shape[0]
    if n <= max_points:
        return points
    rng = np.random.default_rng(seed)
    idx = rng.choice(n, max_points, replace=False)
    return points[idx]


def _unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def _find_horizontal_plane(points, max_planes=4):
    """Iteratively RANSAC until a near-horizontal plane (the reference surface) is found. Returns (normal, d, full_mask) or None.

    ``normal`` is corrected so normal[1] >= 0 (the camera frame has y down, so the floor normal ~ [0,1,0] points downward).
    ``full_mask`` is the full boolean mask over the original ``points``.
    """
    idx = np.arange(points.shape[0])
    pts = np.asarray(points, dtype=float)
    for k in range(max_planes):
        res = fit_plane_ransac(pts, distance_threshold=0.02, seed=k)
        if res is None:
            break
        normal, d, inliers = res
        if abs(normal[1]) >= 0.7:  # near-horizontal -> reference surface
            full = np.zeros(points.shape[0], dtype=bool)
            full[idx[inliers]] = True
            return normal, d, full
        keep = ~inliers
        pts = pts[keep]
        idx = idx[keep]
    return None


def _fit_vertical_planes(points, up_c, min_points=200, max_planes=8):
    """Iteratively RANSAC vertical planes on the non-floor point cloud. Returns ``[(n_h, inlier_pts), ...]``.

    ``n_h`` is the horizontal unit normal (either orientation), ``inlier_pts`` is a copy of the plane's inlier points.
    """
    remaining = np.asarray(points, dtype=float)
    planes = []
    for k in range(max_planes):
        if remaining.shape[0] < min_points:
            break
        res = fit_plane_ransac(remaining, distance_threshold=0.02, seed=k)
        if res is None:
            break
        normal, _d, inliers = res
        n_h = normal - (normal @ up_c) * up_c
        hn = np.linalg.norm(n_h)
        if hn < 0.5:  # near-horizontal (tabletop etc.): drop and continue
            remaining = remaining[~inliers]
            continue
        n_h = n_h / hn
        if int(inliers.sum()) < min_points:
            break
        planes.append((n_h, remaining[inliers]))
        remaining = remaining[~inliers]
    return planes


def _scene_frame_offsets(graph):
    """Read the reference horizontal surface's top y and the back wall plane z from the scene graph (offset tolerances for alignment).

    Convention: y-up, +z toward the viewer, the reference horizontal surface (the largest horizontal plane in the shot: the floor in a wide shot, the countertop/tabletop in a close-up) has its top at y=0, and the back wall (farthest wall) is at z=0. The reference surface is the scene graph node with the largest base area (``floor`` always counts; an ``object`` must be flat, i.e. thickness D[1] < 0.3), not a hardcoded floor. If the LLM did not zero these exactly, the actual values are read here as a tolerance compensation. Returns ``(ref_y, back_z)``; either is None when the corresponding node is missing.
    """
    if not graph:
        return None, None
    ref_y = None
    ref_area = -1.0
    back_z = None
    for n in graph.get("nodes", []):
        C = n.get("C")
        D = n.get("D")
        if not (isinstance(C, (list, tuple)) and len(C) == 3
                and isinstance(D, (list, tuple)) and len(D) == 3):
            continue
        t = n.get("type")
        if t == "wall":
            far = float(C[2] - D[2] / 2.0)      # the wall's face away from the camera (-z)
            back_z = far if back_z is None else min(back_z, far)
            continue
        if t == "floor":
            area = float(D[0] * D[2])
        elif t == "object" and D[1] < 0.3:
            area = float(D[0] * D[2])
        else:
            continue
        if area > ref_area:
            ref_area = area
            ref_y = float(C[1] + D[1] / 2.0)   # top face (assume no rotation)
    return ref_y, back_z


def estimate_room_transform(reconstruction, graph=None):
    """Estimate the w2c transform ``[R|t]`` (3x4) from room.py's y-up room frame to the DA3 world (camera) frame.

    room.py's convention is "image-anchored": +x = image right (= camera x projected onto the horizontal plane), +y up, +z toward the camera, reference horizontal surface top at y=0, back wall at z=0. Therefore **yaw is always 0** (image right is always camera x), and only up (pitch/roll), depth, and x-offset need to be estimated:
    - the reference horizontal surface normal -> up (pitch/roll) and height;
    - if there is a "confident back wall" (roughly facing the camera and the farthest vertical plane along that normal), use it to fix yaw/depth directly — a fallback for a room that is itself yawed; in a close-up the cabinet front is slanted and the back wall is occluded, so it is rejected;
    - depth takes the 98th percentile of the whole point cloud along forward (capturing the back wall rather than the foreground cabinet front);
    - x-offset takes the lateral component of the reference surface centroid.

    Returns a (3,4) array; returns None when no reference horizontal surface is detected.
    """
    pts = unproject_masked(reconstruction.depth, reconstruction.intrinsics,
                           reconstruction.extrinsics, mask=None)
    if pts.shape[0] < 50:
        return None
    pts = _subsample(pts, _RANSAC_MAX_POINTS)

    floor = _find_horizontal_plane(pts)
    if floor is None:
        return None
    normal_c, d_c, floor_mask = floor
    up_c = -_unit(normal_c)  # camera-frame "up" direction

    # room-frame reference surface top y / back wall plane z offsets (conventionally zero; read actual values for tolerance compensation)
    ref_y, back_z = _scene_frame_offsets(graph)
    ref_y = 0.0 if ref_y is None else float(ref_y)
    back_z = 0.0 if back_z is None else float(back_z)

    ref_pts = pts[floor_mask]

    # scene centroid direction (~ camera forward), used to orient walls
    scene_center = pts.mean(axis=0)
    scene_dir = scene_center - (scene_center @ up_c) * up_c
    sdn = np.linalg.norm(scene_dir)
    scene_dir = scene_dir / sdn if sdn > 1e-6 else np.array([0.0, 0.0, 1.0])

    # vertical planes (walls)
    nonfloor = pts[~floor_mask]
    vplanes = _fit_vertical_planes(nonfloor, up_c)

    # Confident back wall: (1) roughly faces the camera (normal ~ -scene_dir, within ~32deg of head-on),
    # (2) is the farthest vertical plane along that normal. In close-ups the locked foreground cabinet
    # front has a slanted normal (n·scene_dir ~ -0.64, ~50deg off), failing both -> rejected, fall back to yaw=0.
    wall_back = None
    wall_depth = None
    wall_center = None
    if vplanes:
        oriented = []
        for n_h, in_pts in vplanes:
            c = in_pts.mean(axis=0)
            if n_h @ scene_dir > 0:
                n_h = -n_h
            oriented.append((n_h, c))
        facing = [t for t in oriented if float(t[0] @ scene_dir) < -0.85]
        if facing:
            n_back, c_back = max(facing, key=lambda t: -float(t[0] @ t[1]))
            d_back = float(-(n_back @ c_back))
            far_along = float(-np.min(pts @ n_back))   # farthest point distance along this wall's normal
            if far_along <= 1.15 * d_back:             # this wall is the farthest vertical plane (true back wall)
                wall_back = n_back
                wall_depth = d_back
                wall_center = c_back

    if wall_back is not None:
        # the room itself is yawed: the back wall fixes yaw/depth directly; x-offset takes the back wall centroid's lateral component
        back_dir = wall_back
        depth = wall_depth
        right_dir = _unit(np.cross(up_c, back_dir))
        x_offset = float(right_dir @ wall_center)
    else:
        # close-up / no back wall: image-anchored yaw=0 (room x = image right = camera x projected onto the horizontal plane)
        right_dir = np.array([1.0, 0.0, 0.0])
        right_dir = _unit(right_dir - (right_dir @ up_c) * up_c)
        back_dir = _unit(np.cross(right_dir, up_c))
        forward = -back_dir
        depth = float(np.percentile(pts @ forward, 98))
        x_offset = float(ref_pts.mean(axis=0) @ right_dir)

    forward = -back_dir
    right_dir = _unit(np.cross(up_c, back_dir))

    R = np.column_stack([right_dir, up_c, back_dir])  # columns = room x / y / z axes expressed in the camera frame
    t = (-d_c - ref_y) * up_c + (depth + back_z) * forward + x_offset * right_dir

    return np.hstack([R, t.reshape(3, 1)])

"""Depth backprojection and 3D->image projection (pure NumPy).

Corresponds to plan.md flow step 4 "backproject each object's points using its mask and frame depth", and the forward projection in compile's check that "reprojects OBBs back into image space to compare against SAM3 boxes".

Extrinsics use DA3's convention (opencv w2c): ``cam = R @ world + t``, hence ``world = R.T @ (cam - t)``.
"""

import numpy as np


def depth_to_camera_points(depth, intrinsics):
    """Depth map (H,W) + intrinsics K(3,3) -> camera-space point cloud (N,3).

    Only pixels with finite depth > 0 are kept.
    """
    depth = np.asarray(depth, dtype=float)
    K = np.asarray(intrinsics, dtype=float)
    H, W = depth.shape
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    v, u = np.mgrid[0:H, 0:W]
    valid = np.isfinite(depth) & (depth > 0)
    z = depth[valid]
    x = (u[valid] - cx) * z / fx
    y = (v[valid] - cy) * z / fy
    return np.stack([x, y, z], axis=-1)


def camera_to_world(points_cam, extrinsics):
    """Camera points (N,3) + extrinsics [R|t] (3x4, w2c) -> world points (N,3)."""
    ext = np.asarray(extrinsics, dtype=float)
    R = ext[:, :3]
    t = ext[:, 3]
    # world = R.T @ (cam - t) = (cam - t) @ R
    return (np.asarray(points_cam, dtype=float) - t) @ R


def world_to_camera_points(points_world, extrinsics):
    """World points (N,3) + extrinsics [R|t] (3x4, w2c) -> camera points (N,3)."""
    ext = np.asarray(extrinsics, dtype=float)
    R = ext[:3, :3]
    t = ext[:3, 3]
    return (np.asarray(points_world, dtype=float) @ R.T) + t


def unproject_masked(depth, intrinsics, extrinsics, mask=None):
    """Depth map + intrinsics + extrinsics -> world point cloud; ``mask`` is an optional (H,W) bool.

    Returns an (N,3) world-coordinate point cloud.
    """
    depth = np.asarray(depth, dtype=float)
    K = np.asarray(intrinsics, dtype=float)
    H, W = depth.shape
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    v, u = np.mgrid[0:H, 0:W]
    valid = np.isfinite(depth) & (depth > 0)
    if mask is not None:
        valid &= np.asarray(mask, dtype=bool)
    z = depth[valid]
    x = (u[valid] - cx) * z / fx
    y = (v[valid] - cy) * z / fy
    cam = np.stack([x, y, z], axis=-1)
    return camera_to_world(cam, extrinsics)


def project_points(points_world, intrinsics, extrinsics):
    """World points (N,3) + intrinsics K(3,3) + extrinsics [R|t] (3x4, w2c) -> image pixels (N,2) and depth z (N,).

    Projection: ``cam = R @ world + t``; ``u = fx*x/z + cx``, ``v = fy*y/z + cy``.
    Returns ``(uv, z)``, where ``z`` is the camera-space depth (>0 means in front of the camera, usable for filtering).
    """
    cam = world_to_camera_points(points_world, extrinsics)
    z = cam[:, 2]
    K = np.asarray(intrinsics, dtype=float)
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = fx * cam[:, 0] / z + cx
        v = fy * cam[:, 1] / z + cy
    return np.stack([u, v], axis=-1), z

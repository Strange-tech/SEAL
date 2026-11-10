"""OBB fitting and plane detection tests (run directly: python layoutagent/tests/test_fitting.py)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sdk.fitting import (
    upright_obb,
    mask_to_obb,
    fit_plane_ransac,
    detect_floor,
)


def _box_points(xmin, xmax, ymin, ymax, zmin, zmax, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    return np.stack([
        rng.uniform(xmin, xmax, n),
        rng.uniform(ymin, ymax, n),
        rng.uniform(zmin, zmax, n),
    ], axis=-1)


def _rot_y(points, deg):
    a = np.radians(deg)
    R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    return points @ R.T


def test_upright_obb_axis_aligned():
    pts = _box_points(0, 4, 0, 1, 0, 2)
    center, dims, theta = upright_obb(pts)
    assert abs(center[0] - 2) < 0.05 and abs(center[1] - 0.5) < 0.05 and abs(center[2] - 1) < 0.05, center
    assert abs(dims[0] - 4) < 0.05 and abs(dims[1] - 1) < 0.05 and abs(dims[2] - 2) < 0.05, dims
    assert abs(theta[1] % 180) < 1.0, theta
    print("[ok] upright_obb axis-aligned")


def test_upright_obb_rotated():
    pts = _rot_y(_box_points(0, 4, 0, 1, 0, 2), 30)
    center, dims, theta = upright_obb(pts)
    assert abs(dims[0] - 4) < 0.05 and abs(dims[1] - 1) < 0.05 and abs(dims[2] - 2) < 0.05, dims
    # yaw recovered to 30deg (mod 180)
    assert abs((theta[1] - 30) % 180) < 2.0, theta
    print("[ok] upright_obb rotated (yaw recovered)")


def test_mask_to_obb():
    H, W = 11, 11
    K = np.array([[100, 0, 5], [0, 100, 5], [0, 0, 1]], dtype=float)
    ext = np.hstack([np.eye(3), np.zeros((3, 1))])
    depth = np.zeros((H, W))
    mask = np.zeros((H, W), dtype=bool)
    mask[2:9, 2:9] = True
    depth[mask] = 3.0
    obb = mask_to_obb(depth, K, ext, mask, min_points=10)
    assert obb is not None
    center, dims, theta = obb
    # plane facing the camera at depth 3: center z ~ 3, center x/y ~ 0
    assert abs(center[2] - 3.0) < 0.05, center
    assert abs(center[0]) < 0.05 and abs(center[1]) < 0.05, center
    print("[ok] mask_to_obb (front-facing plane)")


def test_fit_plane_ransac():
    rng = np.random.default_rng(0)
    x = rng.uniform(-1, 1, 500)
    z = rng.uniform(-1, 1, 500)
    y = 1.0 + rng.normal(0, 0.005, 500)
    pts = np.stack([x, y, z], axis=-1)
    normal, d, inliers = fit_plane_ransac(pts, distance_threshold=0.02, seed=1)
    assert abs(normal[1] - 1.0) < 0.05, normal
    assert abs(d - 1.0) < 0.05, d
    assert inliers.sum() > 400
    print("[ok] fit_plane_ransac")


def test_detect_floor():
    # floor + one wall, verify the floor OBB is detected
    rng = np.random.default_rng(2)
    floor = np.stack([rng.uniform(-3, 3, 3000), rng.uniform(0, 0.01, 3000), rng.uniform(-2, 2, 3000)], axis=-1)
    wall = np.stack([rng.uniform(-3, 3, 500), rng.uniform(0, 3, 500), np.full(500, 2.0)], axis=-1)
    pts = np.vstack([floor, wall])
    obb = detect_floor(pts, thickness=0.1, seed=3)
    assert obb is not None
    center, dims, theta = obb
    assert abs(center[1] - (-0.05)) < 0.05, center  # center is at half the thickness
    assert abs(dims[0] - 6) < 0.15 and abs(dims[2] - 4) < 0.15, dims
    print("[ok] detect_floor")


if __name__ == "__main__":
    test_upright_obb_axis_aligned()
    test_upright_obb_rotated()
    test_mask_to_obb()
    test_fit_plane_ransac()
    test_detect_floor()
    print("\nALL FITTING TESTS PASSED")

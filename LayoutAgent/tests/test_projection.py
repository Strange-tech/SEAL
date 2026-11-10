"""Depth backprojection tests (run directly: python layoutagent/tests/test_projection.py)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sdk.projection import (
    depth_to_camera_points,
    camera_to_world,
    unproject_masked,
)


def test_identity_backprojection():
    # intrinsics: fx=fy=100, principal point (1,1) (3x3 image center); depth map all 2.0
    K = np.array([[100, 0, 1], [0, 100, 1], [0, 0, 1]], dtype=float)
    depth = np.full((3, 3), 2.0)
    pts = depth_to_camera_points(depth, K)
    # center pixel (u=1, v=1) -> cam = (0, 0, 2)
    idx = np.where((np.abs(pts[:, 0]) < 1e-9) & (np.abs(pts[:, 1]) < 1e-9))[0]
    assert len(idx) == 1
    assert abs(pts[idx[0], 2] - 2.0) < 1e-9
    # 9 pixels in total
    assert pts.shape == (9, 3)
    print("[ok] identity backprojection")


def test_camera_to_world_rotation():
    # rotate 90deg about y: R = [[0,0,1],[0,1,0],[-1,0,0]], t=0
    R = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=float)
    ext = np.hstack([R, np.zeros((3, 1))])
    cam = np.array([[1.0, 0.0, 0.0]])  # camera coordinate x=1
    world = camera_to_world(cam, ext)
    # world = R.T @ cam = R.T @ [1,0,0] = [0,0,1]
    assert np.allclose(world[0], [0, 0, 1])
    print("[ok] camera_to_world rotation")


def test_unproject_masked():
    K = np.array([[100, 0, 1], [0, 100, 1], [0, 0, 1]], dtype=float)
    ext = np.hstack([np.eye(3), np.zeros((3, 1))])
    depth = np.full((3, 3), 2.0)
    mask = np.zeros((3, 3), dtype=bool)
    mask[1, 1] = True  # select only the center pixel
    pts = unproject_masked(depth, K, ext, mask)
    assert pts.shape == (1, 3)
    assert np.allclose(pts[0], [0, 0, 2])
    # no mask -> all 9 points
    pts_all = unproject_masked(depth, K, ext)
    assert pts_all.shape == (9, 3)
    print("[ok] unproject_masked")


if __name__ == "__main__":
    test_identity_backprojection()
    test_camera_to_world_rotation()
    test_unproject_masked()
    print("\nALL PROJECTION TESTS PASSED")

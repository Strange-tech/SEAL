"""OBB geometry primitive tests (run directly: python layoutagent/tests/test_geometry.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sdk.geometry import (
    rotation_matrix,
    rotation_matrix_to_euler,
    obb_corners,
    points_to_obb,
    obbs_overlap,
)


def test_rotation_roundtrip():
    rng = np.random.default_rng(0)
    for _ in range(200):
        theta = rng.uniform(-80, 80, 3)  # avoid gimbal lock
        R = rotation_matrix(theta)
        theta2 = rotation_matrix_to_euler(R)
        R2 = rotation_matrix(theta2)
        assert np.allclose(R, R2, atol=1e-6), (theta, theta2)
    print("[ok] rotation roundtrip")


def test_rotation_identity():
    R = rotation_matrix([0, 0, 0])
    assert np.allclose(R, np.eye(3))
    assert np.allclose(rotation_matrix_to_euler(np.eye(3)), [0, 0, 0], atol=1e-6)
    print("[ok] rotation identity")


def test_obb_corners_identity():
    c = obb_corners([0, 0, 0], [2, 2, 2], [0, 0, 0])
    assert c.shape == (8, 3)
    assert np.allclose(c.min(axis=0), [-1, -1, -1])
    assert np.allclose(c.max(axis=0), [1, 1, 1])
    print("[ok] obb corners identity")


def test_points_to_obb_box():
    rng = np.random.default_rng(1)
    pts = rng.uniform(0, 1, size=(2000, 3)) * np.array([4, 2, 1]) + np.array([1, 2, 3])
    center, dims, theta = points_to_obb(pts)
    assert np.allclose(np.sort(dims), [1, 2, 4], atol=0.1), dims
    assert np.allclose(center, [3, 3, 3.5], atol=0.15), center
    print(f"[ok] points_to_obb box  center={np.round(center, 3)} dims={np.round(dims, 3)} theta={np.round(theta, 1)}")


def test_obbs_overlap():
    a = ([0, 0, 0], [1, 1, 1], [0, 0, 0])
    b = ([0.5, 0, 0], [1, 1, 1], [0, 0, 0])
    c = ([5, 0, 0], [1, 1, 1], [0, 0, 0])
    assert obbs_overlap(a, b) is True
    assert obbs_overlap(a, c) is False
    # full containment also counts as intersecting
    d = ([0, 0, 0], [0.2, 0.2, 0.2], [0, 0, 0])
    assert obbs_overlap(a, d) is True
    # still correct after rotation
    e = ([0, 0, 0], [1, 1, 1], [0, 0, 45])
    f = ([0.6, 0.6, 0], [1, 1, 1], [0, 0, 45])
    g = ([5, 5, 0], [1, 1, 1], [0, 0, 45])
    assert obbs_overlap(e, f) is True
    assert obbs_overlap(e, g) is False
    print("[ok] obbs_overlap")


if __name__ == "__main__":
    test_rotation_roundtrip()
    test_rotation_identity()
    test_obb_corners_identity()
    test_points_to_obb_box()
    test_obbs_overlap()
    print("\nALL GEOMETRY TESTS PASSED")

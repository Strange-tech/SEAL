"""Manhattan regularization tests (run directly: python layoutagent/tests/test_manhattan.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema
from sdk.manhattan import (
    estimate_grid_orientation,
    snap_yaw_to_basis,
    manhattan_regularize_nodes,
)


def test_grid_orientation_axis_aligned():
    # two walls at 0 and two at 90 -> grid orientation 0
    assert abs(estimate_grid_orientation([0, 0, 90, 90]) - 0.0) < 1e-6
    # all walls at 45deg -> grid orientation 45
    assert abs(estimate_grid_orientation([45, 45, 45]) - 45.0) < 1e-6
    print("[ok] grid orientation (axis-aligned / rotated)")


def test_grid_orientation_rotated():
    # grid rotated 20deg overall: wall orientations 20 and 110
    g = estimate_grid_orientation([20, 20, 110, 110])
    assert abs(g - 20.0) < 1e-6, g
    print("[ok] grid orientation (20 deg rotated)")


def test_snap_yaw():
    # 92deg is close to 90deg -> snap to 90
    assert snap_yaw_to_basis(92.0, 0.0) == 90.0
    # 5deg is close to 0deg -> snap to 0
    assert snap_yaw_to_basis(5.0, 0.0) == 0.0
    # 30deg is too far from the grid (>15deg) -> keep
    assert snap_yaw_to_basis(30.0, 0.0) == 30.0
    # grid base 20deg: 22deg should snap to 20
    assert snap_yaw_to_basis(22.0, 20.0) == 20.0
    print("[ok] snap yaw to basis")


def test_manhattan_regularize():
    nodes = [
        schema.make_node("wall_0", "wall", [0, 1.5, -2], [5, 3, 0.16], [0, 2, 0]),
        schema.make_node("wall_1", "wall", [0, 1.5, -2], [5, 3, 0.16], [0, 88, 0]),
        schema.make_node("floor", "floor", [0, -0.05, 0], [6, 0.1, 5], [0, 0, 0]),
        schema.make_node("table", "object", [0, 0.375, 0.5], [1.2, 0.75, 0.8], [0, 3, 0]),
        schema.make_node("sofa", "object", [0, 0.375, 0.5], [1.2, 0.75, 0.8], [0, 33, 0]),
    ]
    out = manhattan_regularize_nodes(nodes)
    assert out[0]["theta"][1] == 0.0      # wall at 2deg snaps to 0
    assert out[1]["theta"][1] == 90.0     # wall at 88deg snaps to 90
    assert out[2]["theta"][1] == 0.0      # floor unchanged
    assert out[3]["theta"][1] == 0.0      # object at 3deg snaps to 0
    assert out[4]["theta"][1] == 33.0     # diagonal 33deg is >15deg from the grid, not force-straightened
    # the original objects are not mutated
    assert nodes[0]["theta"][1] == 2.0
    print("[ok] manhattan regularize nodes")


if __name__ == "__main__":
    test_grid_orientation_axis_aligned()
    test_grid_orientation_rotated()
    test_snap_yaw()
    test_manhattan_regularize()
    print("\nALL MANHATTAN TESTS PASSED")

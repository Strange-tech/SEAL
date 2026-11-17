"""OBB geometry primitives (pure NumPy, no model dependency).

Rotation convention matches LiteReality: ``R = Rx(rx) @ Ry(ry) @ Rz(rz)`` with angles in degrees,
and the local axes x/y/z correspond to dims ``[w, h, l]`` (length / height / thickness).
"""

import numpy as np


def rotation_matrix(theta_deg):
    """Euler angles ``[rx, ry, rz]`` (degrees) -> rotation matrix R = Rx @ Ry @ Rz.

    Returns a 3x3 matrix whose **columns** are the local axes expressed in the world frame (columns 0/1/2 correspond to x/y/z).
    """
    rx, ry, rz = np.radians(np.asarray(theta_deg, dtype=float))
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)

    rx_m = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
    ry_m = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    rz_m = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    return rx_m @ ry_m @ rz_m


def rotation_matrix_to_euler(R, degrees=True):
    """Rotation matrix ``R = Rx @ Ry @ Rz`` -> Euler angles ``[rx, ry, rz]``."""
    R = np.asarray(R, dtype=float)
    sy = float(np.clip(R[0, 2], -1.0, 1.0))
    ry = np.arcsin(sy)
    if np.cos(ry) > 1e-6:
        rx = np.arctan2(-R[1, 2], R[2, 2])
        rz = np.arctan2(-R[0, 1], R[0, 0])
    else:
        # gimbal lock (ry ~ +/-90deg): rx and rz degenerate, fix rz = 0
        rx = np.arctan2(R[2, 1], R[1, 1])
        rz = 0.0
    e = np.array([rx, ry, rz])
    return np.degrees(e) if degrees else e


def obb_corners(center, dims, theta):
    """OBB -> 8 world-space corners, shape (8, 3)."""
    C = np.asarray(center, dtype=float)
    D = np.asarray(dims, dtype=float)
    R = rotation_matrix(theta)
    w, h, l = D
    local = np.array(
        [
            [-w / 2, -h / 2, -l / 2],
            [w / 2, -h / 2, -l / 2],
            [w / 2, h / 2, -l / 2],
            [-w / 2, h / 2, -l / 2],
            [-w / 2, -h / 2, l / 2],
            [w / 2, -h / 2, l / 2],
            [w / 2, h / 2, l / 2],
            [-w / 2, h / 2, l / 2],
        ]
    )
    return (local @ R.T) + C


def points_to_obb(points):
    """Point cloud (N,3) -> minimum OBB (PCA principal axes). Returns ``(center, dims, theta)``.

    center is the OBB geometric center (not the mean), dims are the projected spans along the principal axes, theta is solved from the principal-axis matrix.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] < 2:
        raise ValueError("points must be an (N,3) array with N >= 2")
    mean = pts.mean(axis=0)
    centered = pts - mean
    cov = centered.T @ centered / pts.shape[0]
    _, eigvecs = np.linalg.eigh(cov)  # ascending eigenvalues, columns are eigenvectors
    axes = eigvecs[:, ::-1]  # descending: column 0 is the principal axis
    if np.linalg.det(axes) < 0:
        axes[:, 0] *= -1  # ensure right-handed
    proj = centered @ axes
    mins, maxs = proj.min(axis=0), proj.max(axis=0)
    dims = maxs - mins
    center = mean + axes @ ((mins + maxs) / 2.0)
    theta = rotation_matrix_to_euler(axes)
    return center, dims, theta


def obbs_overlap(a, b):
    """Whether two OBBs intersect (separating axis theorem, SAT). a/b are ``(center, dims, theta)``.

    15 separating axes: A's 3 principal axes, B's 3 principal axes, and the 9 cross-product axes.
    No overlap on any one axis means they do not intersect.
    """
    ca, da, ta = np.asarray(a[0], float), np.asarray(a[1], float), a[2]
    cb, db, tb = np.asarray(b[0], float), np.asarray(b[1], float), b[2]
    Ra = rotation_matrix(ta)
    Rb = rotation_matrix(tb)
    t = cb - ca
    ha = da / 2.0
    hb = db / 2.0

    axes = [Ra[:, i] for i in range(3)] + [Rb[:, i] for i in range(3)]
    for i in range(3):
        for j in range(3):
            ax = np.cross(Ra[:, i], Rb[:, j])
            n = np.linalg.norm(ax)
            if n > 1e-9:
                axes.append(ax / n)

    for ax in axes:
        ax = ax / (np.linalg.norm(ax) + 1e-12)
        ra = sum(ha[k] * abs(float(np.dot(ax, Ra[:, k]))) for k in range(3))
        rb = sum(hb[k] * abs(float(np.dot(ax, Rb[:, k]))) for k in range(3))
        if abs(float(np.dot(ax, t))) > ra + rb + 1e-9:
            return False
    return True


def aabb(center, dims, theta):
    """Axis-aligned bounding box of an OBB, returns ``(min, max)``."""
    corners = obb_corners(center, dims, theta)
    return corners.min(axis=0), corners.max(axis=0)


def obbs_gap(a, b):
    """Minimum separation distance between two OBBs (0 if they touch or intersect).

    Mirrors ``obbs_overlap``'s 15-axis SAT projection. For every axis that actually
    separates the two boxes, record the projected separation; the smallest such value
    is the gap. If no axis separates, the boxes intersect or touch, so the gap is 0.
    """
    ca, da, ta = np.asarray(a[0], float), np.asarray(a[1], float), a[2]
    cb, db, tb = np.asarray(b[0], float), np.asarray(b[1], float), b[2]
    Ra = rotation_matrix(ta)
    Rb = rotation_matrix(tb)
    t = cb - ca
    ha = da / 2.0
    hb = db / 2.0

    axes = [Ra[:, i] for i in range(3)] + [Rb[:, i] for i in range(3)]
    for i in range(3):
        for j in range(3):
            ax = np.cross(Ra[:, i], Rb[:, j])
            n = np.linalg.norm(ax)
            if n > 1e-9:
                axes.append(ax / n)

    gap = None
    for ax in axes:
        ax = ax / (np.linalg.norm(ax) + 1e-12)
        ra = sum(ha[k] * abs(float(np.dot(ax, Ra[:, k]))) for k in range(3))
        rb = sum(hb[k] * abs(float(np.dot(ax, Rb[:, k]))) for k in range(3))
        sep = abs(float(np.dot(ax, t))) - (ra + rb)
        if sep > 1e-9:
            gap = sep if gap is None else min(gap, sep)
    return 0.0 if gap is None else float(gap)

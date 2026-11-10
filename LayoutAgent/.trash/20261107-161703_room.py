from __future__ import annotations


def build_scene_graph() -> dict:
    """返回 scene graph：{"nodes": [...], "edges": [...]}。

    node = {"id", "type", "C", "D", "theta"}
      - type: wall | floor | door | window | object
      - C: OBB 中心 [x, y, z]（米），D: 尺寸 [w, h, l]（非负），theta: 欧拉角 [rx, ry, rz]（度）
    edge = {"type", "src", "dst"}
      - type: embedded_in | adjacent | abuts | overlaps_ok
    """
    return {
        "nodes": [],
        "edges": [],
    }

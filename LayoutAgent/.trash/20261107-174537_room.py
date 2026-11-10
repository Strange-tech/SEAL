from __future__ import annotations


def build_scene_graph() -> dict:
    """返回 scene graph：{"nodes": [...], "edges": [...]}。

    node = {"id", "type", "C", "D", "theta"}
      - type: wall | floor | door | window | object
      - C: OBB 中心 [x, y, z]（米），D: 尺寸 [w, h, l]（非负），theta: 欧拉角 [rx, ry, rz]（度）
    edge = {"type", "src", "dst"}
      - type: embedded_in | adjacent | abuts | overlaps_ok

    坐标系约定（必须遵守，右手系 y-up）：
      - +x 右、+y 上、+z 指向相机（观者）；
      - 参考水平面（画面中最大的水平面：宽景是地板，特写是台面/桌面）顶面在 y=0，
        back wall（最远的墙）在 z=0；
      - 只重建画面里看得见的东西：拍不到地板就不要声明 floor 节点，把台面/桌面当参考面
        放在 y=0；
      - 从 da3_reconstruct / backproject_obb 的相机系（x 右 / y 下 / z 前，相机在原点）
        换算到房间系：
            room_x =  cam_x
            room_y = -cam_y + h   # h = 相机到参考水平面的高度（参考面在相机系 cy=h）
            room_z = -cam_z + D   # D = 相机到 back wall 的距离（back wall 在相机系 cz=D）
        （即先翻转 y、z 符号，再整体平移使参考面顶面归 0、back wall 归 0。）
    """
    return {
        "nodes": [],
        "edges": [],
    }

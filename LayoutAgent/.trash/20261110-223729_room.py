from __future__ import annotations


def build_scene_graph() -> dict:
    """Return a scene graph: {"nodes": [...], "edges": [...]}.

    node = {"id", "type", "C", "D", "theta"}
      - type: wall | floor | door | window | object
      - C: OBB center [x, y, z] (meters), D: size [w, h, l] (non-negative), theta: Euler angles [rx, ry, rz] (degrees)
    edge = {"type", "src", "dst"}
      - type: embedded_in | adjacent | abuts | overlaps_ok

    Coordinate convention (must be followed, right-handed y-up):
      - +x right, +y up, +z toward the camera (viewer);
      - the reference horizontal surface (the largest horizontal plane in the shot: the floor in a
        wide shot, the countertop/tabletop in a close-up) has its top at y=0, and the back wall
        (farthest wall) is at z=0;
      - reconstruct only what is actually visible: if the floor is not in frame, do not declare a
        floor node — put the countertop/tabletop at y=0 as the reference surface;
      - to convert from the da3_reconstruct / backproject_obb camera frame (x right / y down / z
        forward, camera at origin) to the room frame:
            room_x =  cam_x
            room_y = -cam_y + h   # h = camera height above the reference horizontal surface (the surface is at camera-space cy=h)
            room_z = -cam_z + D   # D = camera-to-back-wall distance (the back wall is at camera-space cz=D)
        (i.e. flip the y and z signs, then translate so the reference surface top and the back wall are both 0.)
        NOTE: this flip is exact only for a level camera; with camera pitch/roll, use the SDK's
        alignment routine (``sdk.alignment.estimate_room_transform``) for the exact rotation.
    """
    return {
        "nodes": [],
        "edges": [],
    }

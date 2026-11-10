from __future__ import annotations


def build_scene_graph() -> dict:
    """Reconstruct a street traffic scene (elevated view over a cobbled plaza).

    Reference surface = the street/ground (top at y=0). +x right, +y up, +z toward
    the camera. Objects are placed by their relative depth ordering and lateral
    position observed in the image, with real-world metric dimensions.
    """
    floor = {"id": "street", "type": "floor", "C": [0.0, -0.05, 33.0],
             "D": [46.0, 0.1, 70.0], "theta": [0, 0, 0]}

    def car(id_, x, z, w, h, l, yaw=0.0):
        return {"id": id_, "type": "object", "C": [x, h / 2.0, z],
                "D": [w, h, l], "theta": [0, yaw, 0]}

    nodes = [
        floor,
        # foreground / near
        car("suv_white", -6.0, 60.0, 1.95, 1.75, 4.4, -12.0),
        car("car_silver", -0.5, 62.0, 1.70, 1.45, 3.8, 5.0),
        car("taxi_car_right", 6.5, 58.0, 4.00, 1.45, 1.7, 0.0),
        # midground
        car("hatchback_green", -3.5, 52.0, 1.75, 1.55, 3.9, 8.0),
        car("van_white", -0.2, 40.0, 2.00, 1.90, 4.9, -15.0),
        car("taxi_car_left", -3.0, 42.0, 1.70, 1.45, 4.0, 0.0),
        car("taxi_car_center", 3.0, 26.0, 1.70, 1.45, 4.0, -80.0),
        # two-wheelers
        car("scooter_left", -5.0, 47.0, 0.80, 1.20, 2.0, 0.0),
        car("scooter_right", 1.0, 50.0, 0.80, 1.20, 2.0, 0.0),
        # right foreground ornate lamppost
        {"id": "lamppost", "type": "object", "C": [7.5, 3.0, 55.0],
         "D": [0.6, 6.0, 0.6], "theta": [0, 0, 0]},
        # background buses / pedestrians
        {"id": "city_bus", "type": "object", "C": [4.5, 1.55, 8.0],
         "D": [12.0, 3.1, 2.5], "theta": [0, 0, 0]},
        {"id": "coach_bus", "type": "object", "C": [10.7, 1.75, 15.0],
         "D": [12.0, 3.5, 2.5], "theta": [0, 0, 0]},
        {"id": "pedestrians_group", "type": "object", "C": [-6.0, 0.85, 12.0],
         "D": [3.0, 1.7, 1.5], "theta": [0, 0, 0]},
    ]

    grounded = [n["id"] for n in nodes if n["type"] == "object"]
    edges = [{"type": "abuts", "src": oid, "dst": "street"} for oid in grounded]
    edges.append({"type": "adjacent", "src": "taxi_car_center", "dst": "van_white"})

    return {"nodes": nodes, "edges": edges}

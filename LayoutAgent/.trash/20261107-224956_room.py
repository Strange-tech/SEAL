from __future__ import annotations


def build_scene_graph() -> dict:
    """Kitchen counter coffee-brewing close-up.

    Reference surface: the countertop (top at y=0). The floor is not visible in
    the frame, so it is not declared. Back (window) wall at z=0, +z toward camera.
    """
    nodes = [
        # structure ---------------------------------------------------------
        {"id": "countertop", "type": "object",
         "C": [0.0, -0.04, 0.80], "D": [1.90, 0.08, 0.90], "theta": [0, 0, 0]},
        {"id": "back_wall", "type": "wall",
         "C": [0.0, 1.20, -0.08], "D": [3.00, 2.40, 0.16], "theta": [0, 0, 0]},
        {"id": "window", "type": "window",
         "C": [0.05, 1.40, 0.0], "D": [1.70, 1.20, 0.06], "theta": [0, 0, 0]},
        {"id": "cabinet_front", "type": "object",
         "C": [0.55, -0.43, 1.20], "D": [0.80, 0.70, 0.06], "theta": [0, 0, 0]},

        # brew station ------------------------------------------------------
        {"id": "coffee_scale", "type": "object",
         "C": [-0.15, 0.0175, 1.10], "D": [0.23, 0.035, 0.19], "theta": [0, 0, 0]},
        {"id": "glass_server", "type": "object",
         "C": [-0.15, 0.10, 1.10], "D": [0.16, 0.13, 0.16], "theta": [0, 0, 0]},
        {"id": "dripper", "type": "object",
         "C": [-0.15, 0.225, 1.10], "D": [0.13, 0.12, 0.13], "theta": [0, 0, 0]},

        # espresso grinder and beans ---------------------------------------
        {"id": "grinder", "type": "object",
         "C": [0.21, 0.17, 0.45], "D": [0.17, 0.34, 0.17], "theta": [0, 0, 0]},
        {"id": "wooden_board", "type": "object",
         "C": [-0.03, 0.01, 0.62], "D": [0.30, 0.02, 0.30], "theta": [0, 0, 0]},
        {"id": "bean_jar", "type": "object",
         "C": [-0.03, 0.10, 0.62], "D": [0.12, 0.16, 0.12], "theta": [0, 0, 0]},
        {"id": "coffee_cup", "type": "object",
         "C": [0.34, 0.0375, 0.58], "D": [0.09, 0.075, 0.09], "theta": [0, 0, 0]},
        {"id": "cloth", "type": "object",
         "C": [0.62, 0.015, 0.75], "D": [0.22, 0.03, 0.14], "theta": [0, 0, 0]},

        # plants ------------------------------------------------------------
        {"id": "left_plant_stand", "type": "object",
         "C": [-0.42, 0.05, 0.95], "D": [0.26, 0.10, 0.26], "theta": [0, 0, 0]},
        {"id": "left_plant_pot", "type": "object",
         "C": [-0.42, 0.20, 0.95], "D": [0.22, 0.20, 0.22], "theta": [0, 0, 0]},
        {"id": "left_plant_foliage", "type": "object",
         "C": [-0.42, 0.44, 0.95], "D": [0.40, 0.32, 0.36], "theta": [0, 0, 0]},
        {"id": "right_plant_pot", "type": "object",
         "C": [0.52, 0.12, 0.32], "D": [0.20, 0.24, 0.20], "theta": [0, 0, 0]},
        {"id": "right_plant_foliage", "type": "object",
         "C": [0.52, 0.40, 0.32], "D": [0.36, 0.32, 0.34], "theta": [0, 0, 0]},
    ]

    edges = [
        {"type": "embedded_in", "src": "window", "dst": "back_wall"},
        {"type": "adjacent", "src": "cabinet_front", "dst": "countertop"},
        {"type": "abuts", "src": "coffee_scale", "dst": "countertop"},
        {"type": "abuts", "src": "glass_server", "dst": "coffee_scale"},
        {"type": "abuts", "src": "dripper", "dst": "glass_server"},
        {"type": "abuts", "src": "grinder", "dst": "countertop"},
        {"type": "abuts", "src": "wooden_board", "dst": "countertop"},
        {"type": "abuts", "src": "bean_jar", "dst": "wooden_board"},
        {"type": "abuts", "src": "coffee_cup", "dst": "countertop"},
        {"type": "abuts", "src": "cloth", "dst": "countertop"},
        {"type": "abuts", "src": "left_plant_stand", "dst": "countertop"},
        {"type": "abuts", "src": "left_plant_pot", "dst": "left_plant_stand"},
        {"type": "overlaps_ok", "src": "left_plant_foliage", "dst": "left_plant_pot"},
        {"type": "abuts", "src": "right_plant_pot", "dst": "countertop"},
        {"type": "abuts", "src": "right_plant_foliage", "dst": "right_plant_pot"},
    ]

    return {"nodes": nodes, "edges": edges}

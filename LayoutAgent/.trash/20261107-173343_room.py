from __future__ import annotations


def build_scene_graph() -> dict:
    """Coffee-counter kitchen scene reconstruct from a single image.

    Room frame: y-up, floor top at y=0, back wall front face at z=0.
    Counter sits against the back wall; coffee setup on top.
    """
    CTOP = 0.92          # counter top surface height
    nodes = [
        # --- structure ---
        {"id": "floor", "type": "floor",
         "C": [0.0, -0.05, 1.2], "D": [4.0, 0.1, 2.4], "theta": [0, 0, 0]},
        {"id": "back_wall", "type": "wall",
         "C": [0.0, 1.3, 0.0], "D": [4.0, 2.6, 0.16], "theta": [0, 0, 0]},
        {"id": "window", "type": "window",
         "C": [0.35, 1.55, 0.0], "D": [1.5, 1.1, 0.16], "theta": [0, 0, 0]},

        # --- counter base + worktop ---
        {"id": "base_cabinet", "type": "object",
         "C": [0.0, 0.435, 0.43], "D": [1.8, 0.87, 0.66], "theta": [0, 0, 0]},
        {"id": "countertop", "type": "object",
         "C": [0.0, 0.895, 0.43], "D": [1.8, 0.05, 0.70], "theta": [0, 0, 0]},

        # --- left potted plant on wooden stand ---
        {"id": "plant_stand_left", "type": "object",
         "C": [-0.72, 0.99, 0.40], "D": [0.20, 0.14, 0.20], "theta": [0, 0, 0]},
        {"id": "plant_pot_left", "type": "object",
         "C": [-0.72, 1.17, 0.40], "D": [0.20, 0.22, 0.20], "theta": [0, 0, 0]},
        {"id": "plant_foliage_left", "type": "object",
         "C": [-0.72, 1.43, 0.40], "D": [0.34, 0.30, 0.34], "theta": [0, 0, 0]},

        # --- coffee scale ---
        {"id": "coffee_scale", "type": "object",
         "C": [-0.28, 0.9375, 0.45], "D": [0.22, 0.035, 0.20], "theta": [0, 0, 0]},

        # --- pour-over carafe + dripper on the scale ---
        {"id": "carafe", "type": "object",
         "C": [-0.28, 1.06, 0.45], "D": [0.16, 0.21, 0.16], "theta": [0, 0, 0]},
        {"id": "dripper", "type": "object",
         "C": [-0.28, 1.245, 0.45], "D": [0.17, 0.16, 0.17], "theta": [0, 0, 0]},

        # --- wooden tray + glass jar of coffee beans ---
        {"id": "wood_tray", "type": "object",
         "C": [0.05, 0.9325, 0.30], "D": [0.34, 0.025, 0.32], "theta": [0, 0, 0]},
        {"id": "beans_jar", "type": "object",
         "C": [0.05, 1.04, 0.30], "D": [0.13, 0.19, 0.13], "theta": [0, 0, 0]},

        # --- electric coffee grinder ---
        {"id": "grinder", "type": "object",
         "C": [0.30, 1.08, 0.22], "D": [0.16, 0.32, 0.18], "theta": [0, 0, 0]},
        {"id": "grinder_hopper", "type": "object",
         "C": [0.30, 1.335, 0.22], "D": [0.16, 0.19, 0.16], "theta": [0, 0, 0]},

        # --- ceramic cup ---
        {"id": "cup", "type": "object",
         "C": [0.50, 0.955, 0.45], "D": [0.09, 0.07, 0.09], "theta": [0, 0, 0]},

        # --- folded cloth right ---
        {"id": "cloth_towel", "type": "object",
         "C": [0.68, 0.930, 0.55], "D": [0.26, 0.02, 0.18], "theta": [0, 0, 0]},

        # --- background plant on right ---
        {"id": "plant_pot_right", "type": "object",
         "C": [0.80, 1.01, 0.24], "D": [0.16, 0.18, 0.16], "theta": [0, 0, 0]},
        {"id": "plant_foliage_right", "type": "object",
         "C": [0.80, 1.36, 0.24], "D": [0.26, 0.34, 0.24], "theta": [0, 0, 0]},
    ]

    edges = [
        # window embedded in the back wall
        {"type": "embedded_in", "src": "window", "dst": "back_wall"},

        # counter assembly
        {"type": "abuts", "src": "base_cabinet", "dst": "floor"},
        {"type": "abuts", "src": "countertop", "dst": "base_cabinet"},
        {"type": "adjacent", "src": "countertop", "dst": "back_wall"},

        # left plant stack
        {"type": "abuts", "src": "plant_stand_left", "dst": "countertop"},
        {"type": "abuts", "src": "plant_pot_left", "dst": "plant_stand_left"},
        {"type": "abuts", "src": "plant_foliage_left", "dst": "plant_pot_left"},

        # scale and carafe stack
        {"type": "abuts", "src": "coffee_scale", "dst": "countertop"},
        {"type": "abuts", "src": "carafe", "dst": "coffee_scale"},
        {"type": "abuts", "src": "dripper", "dst": "carafe"},

        # tray + jar
        {"type": "abuts", "src": "wood_tray", "dst": "countertop"},
        {"type": "abuts", "src": "beans_jar", "dst": "wood_tray"},

        # grinder
        {"type": "abuts", "src": "grinder", "dst": "countertop"},
        {"type": "abuts", "src": "grinder_hopper", "dst": "grinder"},

        # small tabletop items
        {"type": "abuts", "src": "cup", "dst": "countertop"},
        {"type": "abuts", "src": "cloth_towel", "dst": "countertop"},

        # background right plant
        {"type": "abuts", "src": "plant_pot_right", "dst": "countertop"},
        {"type": "abuts", "src": "plant_foliage_right", "dst": "plant_pot_right"},
    ]

    return {"nodes": nodes, "edges": edges}

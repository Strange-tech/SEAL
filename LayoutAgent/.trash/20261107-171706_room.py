from __future__ import annotations


def build_scene_graph() -> dict:
    """Reconstructed kitchen counter coffee scene (y-up, meters)."""
    nodes = [
        # --- structure ---
        {"id": "floor", "type": "floor", "C": [0.0, -0.05, 1.0], "D": [4.0, 0.1, 4.0], "theta": [0, 0, 0]},
        {"id": "back_wall", "type": "wall", "C": [0.0, 1.2, 1.80], "D": [3.0, 2.4, 0.16], "theta": [0, 0, 0]},
        {"id": "left_wall", "type": "wall", "C": [-1.45, 1.2, 0.70], "D": [0.16, 2.4, 2.2], "theta": [0, 90, 0]},
        {"id": "window", "type": "window", "C": [-0.1, 1.3, 1.80], "D": [2.2, 1.0, 0.16], "theta": [0, 0, 0]},

        # --- counter (base cabinet / countertop) ---
        {"id": "counter", "type": "object", "C": [0.0, 0.45, 1.35], "D": [2.4, 0.90, 0.70], "theta": [0, 0, 0]},

        # --- pour-over cluster on the scale ---
        {"id": "scale", "type": "object", "C": [-0.25, 0.930, 1.28], "D": [0.32, 0.05, 0.26], "theta": [0, 0, 0]},
        {"id": "carafe", "type": "object", "C": [-0.25, 1.060, 1.28], "D": [0.18, 0.20, 0.18], "theta": [0, 0, 0]},
        {"id": "dripper", "type": "object", "C": [-0.25, 1.245, 1.28], "D": [0.16, 0.16, 0.16], "theta": [0, 0, 0]},

        # --- coffee beans in jar on a wooden board ---
        {"id": "board", "type": "object", "C": [0.15, 0.920, 1.52], "D": [0.32, 0.03, 0.30], "theta": [0, 0, 0]},
        {"id": "bean_jar", "type": "object", "C": [0.15, 1.055, 1.52], "D": [0.14, 0.20, 0.14], "theta": [0, 0, 0]},

        # --- coffee grinder ---
        {"id": "grinder_body", "type": "object", "C": [0.55, 1.055, 1.55], "D": [0.18, 0.30, 0.18], "theta": [0, 0, 0]},
        {"id": "grinder_hopper", "type": "object", "C": [0.55, 1.330, 1.55], "D": [0.22, 0.24, 0.20], "theta": [0, 0, 0]},

        # --- mug, folded cloth ---
        {"id": "mug", "type": "object", "C": [0.30, 0.950, 1.30], "D": [0.09, 0.09, 0.09], "theta": [0, 0, 0]},
        {"id": "cloth", "type": "object", "C": [0.65, 0.935, 1.35], "D": [0.28, 0.06, 0.26], "theta": [0, 0, 0]},

        # --- potted plant left (on wooden stand) ---
        {"id": "stand_0", "type": "object", "C": [-0.95, 0.935, 1.45], "D": [0.30, 0.06, 0.28], "theta": [0, 0, 0]},
        {"id": "pot_0", "type": "object", "C": [-0.95, 1.110, 1.45], "D": [0.24, 0.28, 0.24], "theta": [0, 0, 0]},
        {"id": "foliage_0", "type": "object", "C": [-0.95, 1.465, 1.45], "D": [0.45, 0.42, 0.42], "theta": [0, 0, 0]},

        # --- potted plant right near window ---
        {"id": "pot_1", "type": "object", "C": [1.05, 1.035, 1.55], "D": [0.22, 0.26, 0.22], "theta": [0, 0, 0]},
        {"id": "foliage_1", "type": "object", "C": [1.05, 1.420, 1.55], "D": [0.42, 0.50, 0.30], "theta": [0, 0, 0]},
    ]

    edges = [
        {"type": "embedded_in", "src": "window", "dst": "back_wall"},
        {"type": "overlaps_ok", "src": "back_wall", "dst": "left_wall"},
        {"type": "adjacent", "src": "counter", "dst": "back_wall"},

        {"type": "abuts", "src": "scale", "dst": "counter"},
        {"type": "abuts", "src": "carafe", "dst": "scale"},
        {"type": "abuts", "src": "dripper", "dst": "carafe"},

        {"type": "abuts", "src": "board", "dst": "counter"},
        {"type": "abuts", "src": "bean_jar", "dst": "board"},

        {"type": "abuts", "src": "grinder_body", "dst": "counter"},
        {"type": "abuts", "src": "grinder_hopper", "dst": "grinder_body"},

        {"type": "abuts", "src": "mug", "dst": "counter"},
        {"type": "abuts", "src": "cloth", "dst": "counter"},

        {"type": "abuts", "src": "stand_0", "dst": "counter"},
        {"type": "abuts", "src": "pot_0", "dst": "stand_0"},
        {"type": "abuts", "src": "foliage_0", "dst": "pot_0"},

        {"type": "abuts", "src": "pot_1", "dst": "counter"},
        {"type": "abuts", "src": "foliage_1", "dst": "pot_1"},
    ]

    return {"nodes": nodes, "edges": edges}

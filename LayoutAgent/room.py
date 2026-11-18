from __future__ import annotations


def build_scene_graph() -> dict:
    """Living room: sofa, dining table with 3 chairs, and a wall TV."""
    nodes = [
        # Floor: top at y=0
        {"id": "floor", "type": "floor", "C": [2.5, -0.05, 2.75], "D": [5.0, 0.1, 5.5], "theta": [0, 0, 0]},

        # Enclosing walls (2.6 m tall, 0.16 m thick), +Z inward
        {"id": "back_wall", "type": "wall", "C": [2.5, 1.3, 0.0], "D": [5.0, 2.6, 0.16], "theta": [0, 0, 0]},
        {"id": "front_wall", "type": "wall", "C": [2.5, 1.3, 5.5], "D": [5.0, 2.6, 0.16], "theta": [0, 180, 0]},
        {"id": "left_wall", "type": "wall", "C": [0.0, 1.3, 2.75], "D": [5.5, 2.6, 0.16], "theta": [0, 90, 0]},
        {"id": "right_wall", "type": "wall", "C": [5.0, 1.3, 2.75], "D": [5.5, 2.6, 0.16], "theta": [0, -90, 0]},

        # Window recessed into the left wall, centered on its run
        {"id": "left_window", "type": "window", "C": [0.0, 1.5, 2.75], "D": [1.2, 1.2, 0.16], "theta": [0, 90, 0]},

        # Wall-mounted TV, now on the left wall (the sofa's former spot), facing into the room (+x)
        {"id": "tv", "type": "object", "C": [0.12, 1.35, 1.35], "D": [1.2, 0.7, 0.08], "theta": [0, 90, 0]},

        # Sofa, now against the back wall (the TV's former spot), back flush to it, facing into the room (+z)
        {"id": "sofa", "type": "object", "C": [2.5, 0.4, 0.56], "D": [2.2, 0.8, 0.9], "theta": [0, 0, 0]},

        # Floor lamp standing beside the left end of the new sofa
        {"id": "floor_lamp", "type": "object", "class": "floor lamp", "C": [1.18, 0.85, 0.56], "D": [0.42, 1.7, 0.42], "theta": [0, 0, 0]},

        # Side table on the floor just in front of the new sofa, centered on its run
        {"id": "side_table", "type": "object", "class": "side table", "C": [2.0, 0.275, 1.29], "D": [0.45, 0.55, 0.45], "theta": [0, 0, 0]},

        # Dining table, centered in the room
        {"id": "dining_table", "type": "object", "C": [2.5, 0.375, 2.75], "D": [1.4, 0.75, 0.85], "theta": [0, 0, 0]},

        # Three dining chairs around the centered dining table
        {"id": "chair_0", "type": "object", "class": "dining chair", "C": [2.5, 0.45, 2.0], "D": [0.45, 0.9, 0.45], "theta": [0, 0, 0]},
        {"id": "chair_2", "type": "object", "class": "dining chair", "C": [2.1, 0.45, 3.5], "D": [0.45, 0.9, 0.45], "theta": [0, 180, 0]},
        {"id": "chair_3", "type": "object", "class": "dining chair", "C": [2.9, 0.45, 3.5], "D": [0.45, 0.9, 0.45], "theta": [0, 180, 0]},
    ]

    edges = [
        # TV mounted in the left wall
        {"type": "embedded_in", "src": "tv", "dst": "left_wall"},
        {"type": "supports", "src": "tv", "dst": "left_wall"},

        # Window set into the left wall
        {"type": "embedded_in", "src": "left_window", "dst": "left_wall"},
        {"type": "adjacent", "src": "left_window", "dst": "left_wall"},

        # Wall corners intentionally overlap
        {"type": "overlaps_ok", "src": "back_wall", "dst": "left_wall"},
        {"type": "overlaps_ok", "src": "back_wall", "dst": "right_wall"},
        {"type": "overlaps_ok", "src": "front_wall", "dst": "left_wall"},
        {"type": "overlaps_ok", "src": "front_wall", "dst": "right_wall"},

        # Placement relations
        {"type": "supports", "src": "sofa", "dst": "floor"},
        {"type": "adjacent", "src": "sofa", "dst": "back_wall"},
        {"type": "supports", "src": "floor_lamp", "dst": "floor"},
        {"type": "adjacent", "src": "floor_lamp", "dst": "sofa"},
        {"type": "supports", "src": "side_table", "dst": "floor"},
        {"type": "adjacent", "src": "side_table", "dst": "sofa"},
        {"type": "adjacent", "src": "chair_0", "dst": "dining_table"},
        {"type": "adjacent", "src": "chair_2", "dst": "dining_table"},
        {"type": "adjacent", "src": "chair_3", "dst": "dining_table"},
    ]

    return {"nodes": nodes, "edges": edges}

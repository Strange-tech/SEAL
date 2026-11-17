from __future__ import annotations


def build_scene_graph() -> dict:
    """Living room: sofa, coffee table, dining table with 4 chairs, and a wall TV."""
    nodes = [
        # Floor: top at y=0
        {"id": "floor", "type": "floor", "C": [2.5, -0.05, 2.75], "D": [5.0, 0.1, 5.5], "theta": [0, 0, 0]},

        # Enclosing walls (2.6 m tall, 0.16 m thick), +Z inward
        {"id": "back_wall", "type": "wall", "C": [2.5, 1.3, 0.0], "D": [5.0, 2.6, 0.16], "theta": [0, 0, 0]},
        {"id": "front_wall", "type": "wall", "C": [2.5, 1.3, 5.5], "D": [5.0, 2.6, 0.16], "theta": [0, 180, 0]},
        {"id": "left_wall", "type": "wall", "C": [0.0, 1.3, 2.75], "D": [5.5, 2.6, 0.16], "theta": [0, 90, 0]},
        {"id": "right_wall", "type": "wall", "C": [5.0, 1.3, 2.75], "D": [5.5, 2.6, 0.16], "theta": [0, -90, 0]},

        # Wall-mounted TV on the front wall, facing the sofa (-z)
        {"id": "tv", "type": "object", "C": [2.5, 1.5, 5.4], "D": [1.6, 0.9, 0.08], "theta": [0, 180, 0]},

        # Sofa against the back wall, facing into the room (+z)
        {"id": "sofa", "type": "object", "C": [2.5, 0.4, 0.6], "D": [2.2, 0.8, 0.9], "theta": [0, 0, 0]},

        # Coffee table between sofa and TV
        {"id": "coffee_table", "type": "object", "C": [2.5, 0.225, 1.9], "D": [1.2, 0.45, 0.7], "theta": [0, 0, 0]},

        # Dining table
        {"id": "dining_table", "type": "object", "C": [1.3, 0.375, 3.8], "D": [1.4, 0.75, 0.85], "theta": [0, 0, 0]},

        # Four dining chairs around the dining table
        {"id": "chair_0", "type": "object", "class": "dining chair", "C": [0.9, 0.45, 3.05], "D": [0.45, 0.9, 0.45], "theta": [0, 0, 0]},
        {"id": "chair_1", "type": "object", "class": "dining chair", "C": [1.7, 0.45, 3.05], "D": [0.45, 0.9, 0.45], "theta": [0, 0, 0]},
        {"id": "chair_2", "type": "object", "class": "dining chair", "C": [0.9, 0.45, 4.55], "D": [0.45, 0.9, 0.45], "theta": [0, 180, 0]},
        {"id": "chair_3", "type": "object", "class": "dining chair", "C": [1.7, 0.45, 4.55], "D": [0.45, 0.9, 0.45], "theta": [0, 180, 0]},
    ]

    edges = [
        # TV mounted in the front wall
        {"type": "embedded_in", "src": "tv", "dst": "front_wall"},
        {"type": "supports", "src": "tv", "dst": "front_wall"},

        # Wall corners intentionally overlap
        {"type": "overlaps_ok", "src": "back_wall", "dst": "left_wall"},
        {"type": "overlaps_ok", "src": "back_wall", "dst": "right_wall"},
        {"type": "overlaps_ok", "src": "front_wall", "dst": "left_wall"},
        {"type": "overlaps_ok", "src": "front_wall", "dst": "right_wall"},

        # Placement relations
        {"type": "adjacent", "src": "sofa", "dst": "back_wall"},
        {"type": "adjacent", "src": "chair_0", "dst": "dining_table"},
        {"type": "adjacent", "src": "chair_1", "dst": "dining_table"},
        {"type": "adjacent", "src": "chair_2", "dst": "dining_table"},
        {"type": "adjacent", "src": "chair_3", "dst": "dining_table"},
    ]

    return {"nodes": nodes, "edges": edges}

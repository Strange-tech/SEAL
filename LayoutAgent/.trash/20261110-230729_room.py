from __future__ import annotations


def build_scene_graph() -> dict:
    """Office desk scene reconstructed from a single close-up frame.

    Reference surface = desk top near y = 0 (floor not visible, so no floor node).
    +x right, +y up, +z toward the camera, back glass partition near z = 0.
    """
    nodes = [
        # --- reference work surface (close-up: desk top is the reference plane) ---
        {"id": "desk_surface", "type": "object",
         "C": [0.10, -0.035, 0.90], "D": [2.20, 0.05, 0.90], "theta": [0, 0, 0]},

        # --- background glass partition wall ---
        {"id": "glass_partition", "type": "wall",
         "C": [0.10, 1.30, -0.05], "D": [3.20, 2.60, 0.10], "theta": [0, 0, 0]},

        # --- main monitor + stand ---
        {"id": "main_monitor", "type": "object",
         "C": [0.165, 0.37, 0.45], "D": [0.762, 0.44, 0.111], "theta": [0, 0, 0]},
        {"id": "monitor_stand", "type": "object",
         "C": [0.165, 0.07, 0.45], "D": [0.30, 0.14, 0.18], "theta": [0, 0, 0]},

        # --- keyboard / mouse on the mouse pad ---
        {"id": "mousepad", "type": "object",
         "C": [0.19, 0.005, 0.75], "D": [0.80, 0.01, 0.40], "theta": [0, 0, 0]},
        {"id": "keyboard", "type": "object",
         "C": [0.082, 0.045, 0.669], "D": [0.428, 0.05, 0.17], "theta": [0, 0, 0]},
        {"id": "mouse", "type": "object",
         "C": [0.366, 0.045, 0.816], "D": [0.06, 0.05, 0.11], "theta": [0, 0, 0]},

        # --- laptop (closed) at left foreground ---
        {"id": "laptop", "type": "object",
         "C": [-0.55, 0.01, 0.85], "D": [0.32, 0.02, 0.22], "theta": [0, 0, 0]},

        # --- flanking speakers ---
        {"id": "speaker_left", "type": "object",
         "C": [-0.30, 0.125, 0.55], "D": [0.15, 0.25, 0.15], "theta": [0, 0, 0]},
        {"id": "speaker_right", "type": "object",
         "C": [0.68, 0.125, 0.55], "D": [0.15, 0.25, 0.15], "theta": [0, 0, 0]},

        # --- small desk items ---
        {"id": "phone", "type": "object",
         "C": [-0.30, 0.008, 0.75], "D": [0.08, 0.016, 0.16], "theta": [0, 0, 0]},
        {"id": "papers", "type": "object",
         "C": [0.75, 0.006, 0.70], "D": [0.30, 0.012, 0.40], "theta": [0, 0, 0]},

        # --- background ---
        {"id": "background_monitor", "type": "object",
         "C": [-1.05, 0.17, 0.15], "D": [0.50, 0.34, 0.05], "theta": [0, 0, 0]},
        {"id": "background_chair", "type": "object",
         "C": [-0.40, 0.50, 0.20], "D": [0.60, 1.00, 0.30], "theta": [0, 0, 0]},
    ]

    edges = [
        # support (src rests on dst)
        {"type": "abuts", "src": "monitor_stand", "dst": "desk_surface"},
        {"type": "abuts", "src": "main_monitor", "dst": "monitor_stand"},
        {"type": "abuts", "src": "mousepad", "dst": "desk_surface"},
        {"type": "abuts", "src": "keyboard", "dst": "mousepad"},
        {"type": "abuts", "src": "mouse", "dst": "mousepad"},
        {"type": "abuts", "src": "laptop", "dst": "desk_surface"},
        {"type": "abuts", "src": "speaker_left", "dst": "desk_surface"},
        {"type": "abuts", "src": "speaker_right", "dst": "desk_surface"},
        {"type": "abuts", "src": "phone", "dst": "desk_surface"},
        {"type": "abuts", "src": "papers", "dst": "desk_surface"},
        {"type": "abuts", "src": "background_monitor", "dst": "desk_surface"},
        {"type": "abuts", "src": "background_chair", "dst": "desk_surface"},

        # intentional relations
        {"type": "overlaps_ok", "src": "papers", "dst": "speaker_right"},
        {"type": "adjacent", "src": "speaker_left", "dst": "main_monitor"},
        {"type": "adjacent", "src": "speaker_right", "dst": "main_monitor"},
    ]

    return {"nodes": nodes, "edges": edges}

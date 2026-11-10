from __future__ import annotations


def build_scene_graph() -> dict:
    """Office desk scene reconstructed from a single close-up frame.

    Room frame is image-anchored (x right, y up, z toward camera).  Room x is
    measured relative to the reference surface (desk) lateral centroid, so the
    desk slab sits at x=0 and other objects keep their camera-relative offset.
    The desk top is the reference surface (y ~ 0); the floor is not visible so
    no floor node is declared.  Back glass partition near z = 0.
    """
    nodes = [
        # --- reference work surface (desk top is the reference plane) ---
        {"id": "desk_surface", "type": "object",
         "C": [0.00, -0.03, 2.40], "D": [2.60, 0.05, 1.10], "theta": [0, 0, 0]},

        # --- background glass partition wall ---
        {"id": "glass_partition", "type": "wall",
         "C": [0.00, 1.30, -0.05], "D": [3.40, 2.60, 0.10], "theta": [0, 0, 0]},

        # --- main monitor + stand ---
        {"id": "main_monitor", "type": "object",
         "C": [0.485, 0.368, 2.446], "D": [0.762, 0.436, 0.111], "theta": [0, 0, 0]},
        {"id": "monitor_stand", "type": "object",
         "C": [0.485, 0.07, 2.42], "D": [0.30, 0.14, 0.18], "theta": [0, 0, 0]},

        # --- mouse pad / keyboard / mouse ---
        {"id": "mousepad", "type": "object",
         "C": [0.477, 0.005, 2.72], "D": [0.778, 0.01, 0.40], "theta": [0, 0, 0]},
        {"id": "keyboard", "type": "object",
         "C": [0.402, 0.04, 2.669], "D": [0.428, 0.04, 0.17], "theta": [0, 0, 0]},
        {"id": "mouse", "type": "object",
         "C": [0.686, 0.0425, 2.816], "D": [0.06, 0.045, 0.11], "theta": [0, 0, 0]},

        # --- closed laptop (left foreground) ---
        {"id": "laptop", "type": "object",
         "C": [-0.13, 0.015, 2.65], "D": [0.34, 0.03, 0.22], "theta": [0, 0, 0]},

        # --- flanking speakers ---
        {"id": "speaker_left", "type": "object",
         "C": [0.02, 0.125, 2.42], "D": [0.15, 0.25, 0.15], "theta": [0, 0, 0]},
        {"id": "speaker_right", "type": "object",
         "C": [0.98, 0.125, 2.42], "D": [0.15, 0.25, 0.15], "theta": [0, 0, 0]},

        # --- small desk items ---
        {"id": "phone", "type": "object",
         "C": [-0.291, 0.006, 1.987], "D": [0.08, 0.012, 0.16], "theta": [0, 0, 0]},
        {"id": "papers", "type": "object",
         "C": [0.843, 0.006, 2.42], "D": [0.30, 0.012, 0.40], "theta": [0, 0, 0]},

        # --- background ---
        {"id": "background_monitor", "type": "object",
         "C": [-1.137, 0.17, 0.487], "D": [0.50, 0.34, 0.05], "theta": [0, 0, 0]},
        {"id": "background_chair", "type": "object",
         "C": [-0.616, 0.50, 0.18], "D": [0.60, 1.00, 0.30], "theta": [0, 0, 0]},
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

        # intentional relations
        {"type": "overlaps_ok", "src": "papers", "dst": "speaker_right"},
        {"type": "overlaps_ok", "src": "papers", "dst": "mousepad"},
        {"type": "adjacent", "src": "speaker_left", "dst": "main_monitor"},
        {"type": "adjacent", "src": "speaker_right", "dst": "main_monitor"},
    ]

    return {"nodes": nodes, "edges": edges}

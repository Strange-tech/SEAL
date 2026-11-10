from __future__ import annotations

# Camera-to-back-wall depth estimate (metres).  Room z = D - cam_z.
D_BACK = 9.0

# Per-object camera-frame depth (metres, +z into the scene).
_CZ = {
    "desk_surface": 1.10,
    "monitor_stand": 1.08,
    "main_monitor": 1.054,
    "mousepad": 0.78,
    "keyboard": 0.831,
    "mouse": 0.684,
    "laptop": 0.85,
    "speaker_left": 1.08,
    "speaker_right": 1.08,
    "phone": 1.513,
    "papers": 1.08,
    "background_monitor": 3.013,
    "background_chair": 3.32,
}


def _z(name):
    return round(D_BACK - _CZ[name], 3)


def build_scene_graph() -> dict:
    """Office desk scene reconstructed from a single close-up frame.

    Room frame is image-anchored (x right, y up, z toward camera).  Room x is
    relative to the reference surface (desk) lateral centroid (desk at x=0);
    room z places the desk close to the camera with the glass partition as the
    far back wall near z=0.  The desk top is the reference surface (y ~ 0); the
    floor is not visible so no floor node is declared.
    """
    nodes = [
        # --- reference work surface (desk top is the reference plane) ---
        {"id": "desk_surface", "type": "object",
         "C": [0.00, -0.03, _z("desk_surface")], "D": [2.60, 0.05, 1.10], "theta": [0, 0, 0]},

        # --- background glass partition wall ---
        {"id": "glass_partition", "type": "wall",
         "C": [0.00, 1.30, -0.05], "D": [3.40, 2.60, 0.10], "theta": [0, 0, 0]},

        # --- main monitor + stand ---
        {"id": "main_monitor", "type": "object",
         "C": [0.485, 0.368, _z("main_monitor")], "D": [0.762, 0.436, 0.111], "theta": [0, 0, 0]},
        {"id": "monitor_stand", "type": "object",
         "C": [0.485, 0.07, _z("monitor_stand")], "D": [0.30, 0.14, 0.18], "theta": [0, 0, 0]},

        # --- mouse pad / keyboard / mouse ---
        {"id": "mousepad", "type": "object",
         "C": [0.477, 0.005, _z("mousepad")], "D": [0.778, 0.01, 0.40], "theta": [0, 0, 0]},
        {"id": "keyboard", "type": "object",
         "C": [0.402, 0.04, _z("keyboard")], "D": [0.428, 0.04, 0.17], "theta": [0, 0, 0]},
        {"id": "mouse", "type": "object",
         "C": [0.686, 0.0425, _z("mouse")], "D": [0.06, 0.045, 0.11], "theta": [0, 0, 0]},

        # --- closed laptop (left foreground) ---
        {"id": "laptop", "type": "object",
         "C": [-0.13, 0.015, _z("laptop")], "D": [0.34, 0.03, 0.22], "theta": [0, 0, 0]},

        # --- flanking speakers ---
        {"id": "speaker_left", "type": "object",
         "C": [0.02, 0.125, _z("speaker_left")], "D": [0.15, 0.25, 0.15], "theta": [0, 0, 0]},
        {"id": "speaker_right", "type": "object",
         "C": [0.98, 0.125, _z("speaker_right")], "D": [0.15, 0.25, 0.15], "theta": [0, 0, 0]},

        # --- small desk items ---
        {"id": "phone", "type": "object",
         "C": [-0.291, 0.006, _z("phone")], "D": [0.08, 0.012, 0.16], "theta": [0, 0, 0]},
        {"id": "papers", "type": "object",
         "C": [0.843, 0.006, _z("papers")], "D": [0.30, 0.012, 0.40], "theta": [0, 0, 0]},

        # --- background ---
        {"id": "background_monitor", "type": "object",
         "C": [-1.137, 0.17, _z("background_monitor")], "D": [0.50, 0.34, 0.05], "theta": [0, 0, 0]},
        {"id": "background_chair", "type": "object",
         "C": [-0.616, 0.50, _z("background_chair")], "D": [0.60, 1.00, 0.30], "theta": [0, 0, 0]},
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

from __future__ import annotations

# Global yaw of the counter/back-wall run relative to the camera's horizontal axes
# (estimated from the backprojected OBBs of the counter-aligned objects).
YAW = 20.0


def _t(yaw=YAW):
    return [0, yaw, 0]


def build_scene_graph() -> dict:
    """Pour-over coffee station on a kitchen countertop (close-up).

    Room frame: +x right, +y up, +z toward the camera. The countertop top is the
    reference horizontal surface (y = 0); the back wall (with the two windows) is
    at z = 0. No floor is visible, so no floor node is declared.
    """
    nodes = [
        # ---------- foreground: scale + pour-over stack ----------
        {"id": "digital_scale", "type": "object",
         "C": [-0.13, 0.015, 0.94], "D": [0.25, 0.03, 0.20], "theta": _t()},
        {"id": "carafe", "type": "object",
         "C": [-0.14, 0.125, 0.84], "D": [0.16, 0.19, 0.15], "theta": _t()},
        {"id": "dripper", "type": "object",
         "C": [-0.14, 0.285, 0.84], "D": [0.15, 0.13, 0.15], "theta": _t()},
        {"id": "paper_filter", "type": "object",
         "C": [-0.14, 0.280, 0.84], "D": [0.125, 0.115, 0.125], "theta": _t()},

        # ---------- foreground left: plant on a wooden block ----------
        {"id": "wooden_block", "type": "object",
         "C": [-0.37, 0.040, 0.88], "D": [0.20, 0.08, 0.15], "theta": _t()},
        {"id": "plant_pot_left", "type": "object",
         "C": [-0.35, 0.175, 0.92], "D": [0.19, 0.19, 0.19], "theta": _t()},
        {"id": "plant_left", "type": "object",
         "C": [-0.34, 0.450, 0.87], "D": [0.45, 0.36, 0.40], "theta": _t()},

        # ---------- midground ----------
        {"id": "saucer", "type": "object",
         "C": [0.19, 0.006, 0.62], "D": [0.14, 0.012, 0.14], "theta": _t()},
        {"id": "cup", "type": "object",
         "C": [0.19, 0.0495, 0.62], "D": [0.085, 0.075, 0.085], "theta": _t()},
        {"id": "cloth", "type": "object",
         "C": [0.42, 0.006, 0.55], "D": [0.25, 0.012, 0.17], "theta": _t()},
        {"id": "wooden_board", "type": "object",
         "C": [0.01, 0.011, 0.67], "D": [0.28, 0.022, 0.28], "theta": _t()},
        {"id": "glass_jar", "type": "object",
         "C": [0.00, 0.117, 0.58], "D": [0.13, 0.19, 0.13], "theta": _t()},
        {"id": "coffee_beans", "type": "object",
         "C": [0.00, 0.085, 0.58], "D": [0.10, 0.09, 0.10], "theta": _t()},

        # ---------- background: grinder and the second plant ----------
        {"id": "coffee_grinder", "type": "object",
         "C": [0.18, 0.150, 0.35], "D": [0.20, 0.30, 0.20], "theta": _t()},
        {"id": "grinder_hopper", "type": "object",
         "C": [0.18, 0.390, 0.35], "D": [0.16, 0.18, 0.16], "theta": _t()},
        {"id": "plant_pot_right", "type": "object",
         "C": [0.41, 0.0875, 0.12], "D": [0.20, 0.175, 0.20], "theta": _t()},
        {"id": "plant_right", "type": "object",
         "C": [0.41, 0.355, 0.18], "D": [0.50, 0.36, 0.40], "theta": _t()},

        # ---------- fixtures ----------
        {"id": "countertop", "type": "object",
         "C": [0.12, -0.025, 0.55], "D": [2.60, 0.05, 0.94], "theta": _t()},
        {"id": "counter_cabinet", "type": "object",
         "C": [0.75, -0.47, 0.60], "D": [0.90, 0.82, 0.85], "theta": _t()},
        {"id": "backsplash", "type": "object",
         "C": [0.10, 0.26, 0.005], "D": [2.60, 0.52, 0.02], "theta": _t()},
        {"id": "wall_back", "type": "wall",
         "C": [0.10, 1.20, -0.08], "D": [2.60, 2.40, 0.16], "theta": _t()},
        {"id": "window_center", "type": "window",
         "C": [-0.15, 1.13, 0.00], "D": [0.75, 1.14, 0.10], "theta": _t()},
        {"id": "window_right", "type": "window",
         "C": [0.66, 1.13, 0.00], "D": [0.55, 1.14, 0.10], "theta": _t()},
    ]

    edges = [
        # --- embedded / intentional surface layering ---
        {"type": "embedded_in", "src": "window_center", "dst": "wall_back"},
        {"type": "embedded_in", "src": "window_right", "dst": "wall_back"},
        {"type": "overlaps_ok", "src": "backsplash", "dst": "wall_back"},

        # --- pour-over stack ---
        {"type": "abuts", "src": "digital_scale", "dst": "countertop"},
        {"type": "abuts", "src": "carafe", "dst": "digital_scale"},
        {"type": "abuts", "src": "dripper", "dst": "carafe"},
        {"type": "overlaps_ok", "src": "paper_filter", "dst": "dripper"},

        # --- jar of beans on the round board ---
        {"type": "abuts", "src": "wooden_board", "dst": "countertop"},
        {"type": "abuts", "src": "glass_jar", "dst": "wooden_board"},
        {"type": "overlaps_ok", "src": "coffee_beans", "dst": "glass_jar"},

        # --- cup and saucer ---
        {"type": "abuts", "src": "saucer", "dst": "countertop"},
        {"type": "abuts", "src": "cup", "dst": "saucer"},
        {"type": "adjacent", "src": "saucer", "dst": "glass_jar"},

        # --- grinder ---
        {"type": "abuts", "src": "coffee_grinder", "dst": "countertop"},
        {"type": "abuts", "src": "grinder_hopper", "dst": "coffee_grinder"},
        {"type": "adjacent", "src": "coffee_grinder", "dst": "glass_jar"},

        # --- plants ---
        {"type": "abuts", "src": "wooden_block", "dst": "countertop"},
        {"type": "abuts", "src": "plant_pot_left", "dst": "wooden_block"},
        {"type": "abuts", "src": "plant_left", "dst": "plant_pot_left"},
        {"type": "abuts", "src": "plant_pot_right", "dst": "countertop"},
        {"type": "abuts", "src": "plant_right", "dst": "plant_pot_right"},

        # --- rest of the props / structure ---
        {"type": "abuts", "src": "cloth", "dst": "countertop"},
        {"type": "abuts", "src": "countertop", "dst": "counter_cabinet"},
        {"type": "adjacent", "src": "backsplash", "dst": "countertop"},
        {"type": "adjacent", "src": "plant_pot_right", "dst": "window_right"},

        # --- face-to-face contact (audited as intersecting OBBs) ---
        {"type": "overlaps_ok", "src": "digital_scale", "dst": "countertop"},
        {"type": "overlaps_ok", "src": "carafe", "dst": "digital_scale"},
        {"type": "overlaps_ok", "src": "dripper", "dst": "carafe"},
        {"type": "overlaps_ok", "src": "wooden_block", "dst": "countertop"},
        {"type": "overlaps_ok", "src": "plant_pot_left", "dst": "wooden_block"},
        {"type": "overlaps_ok", "src": "plant_left", "dst": "plant_pot_left"},
        {"type": "overlaps_ok", "src": "saucer", "dst": "countertop"},
        {"type": "overlaps_ok", "src": "cup", "dst": "saucer"},
        {"type": "overlaps_ok", "src": "cloth", "dst": "countertop"},
        {"type": "overlaps_ok", "src": "wooden_board", "dst": "countertop"},
        {"type": "overlaps_ok", "src": "glass_jar", "dst": "wooden_board"},
        {"type": "overlaps_ok", "src": "coffee_grinder", "dst": "countertop"},
        {"type": "overlaps_ok", "src": "grinder_hopper", "dst": "coffee_grinder"},
        {"type": "overlaps_ok", "src": "plant_pot_right", "dst": "countertop"},
        {"type": "overlaps_ok", "src": "plant_right", "dst": "plant_pot_right"},
    ]

    return {"nodes": nodes, "edges": edges}

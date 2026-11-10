from __future__ import annotations


def build_scene_graph() -> dict:
    """Pour-over coffee station on a kitchen countertop (close-up).

    Room frame: +x right, +y up, +z toward the camera. The countertop top is the
    reference horizontal surface (y = 0); the back wall is at z = 0.
    No floor is visible in this close-up, so no floor node is declared.
    """
    nodes = [
        # ---------- foreground / closest to camera ----------
        {"id": "digital_scale", "type": "object",
         "C": [-0.45, 0.0175, 0.58], "D": [0.24, 0.035, 0.19], "theta": [0, 0, 0]},
        {"id": "carafe", "type": "object",
         "C": [-0.45, 0.110, 0.58], "D": [0.17, 0.15, 0.16], "theta": [0, 0, 0]},
        {"id": "dripper", "type": "object",
         "C": [-0.45, 0.250, 0.58], "D": [0.145, 0.13, 0.145], "theta": [0, 0, 0]},
        {"id": "paper_filter", "type": "object",
         "C": [-0.45, 0.245, 0.58], "D": [0.120, 0.115, 0.120], "theta": [0, 0, 0]},
        {"id": "wooden_block", "type": "object",
         "C": [-1.02, 0.045, 0.58], "D": [0.19, 0.09, 0.15], "theta": [0, 0, 0]},
        {"id": "plant_pot_left", "type": "object",
         "C": [-1.02, 0.190, 0.58], "D": [0.20, 0.20, 0.20], "theta": [0, 0, 0]},
        {"id": "plant_left", "type": "object",
         "C": [-1.02, 0.470, 0.56], "D": [0.46, 0.36, 0.36], "theta": [0, 0, 0]},
        {"id": "cloth", "type": "object",
         "C": [0.88, 0.006, 0.50], "D": [0.24, 0.012, 0.16], "theta": [0, 0, 0]},

        # ---------- midground ----------
        {"id": "saucer", "type": "object",
         "C": [0.40, 0.006, 0.44], "D": [0.145, 0.012, 0.145], "theta": [0, 0, 0]},
        {"id": "cup", "type": "object",
         "C": [0.40, 0.0495, 0.44], "D": [0.085, 0.075, 0.085], "theta": [0, 0, 0]},
        {"id": "wooden_board", "type": "object",
         "C": [0.00, 0.011, 0.40], "D": [0.30, 0.022, 0.30], "theta": [0, 0, 0]},
        {"id": "glass_jar", "type": "object",
         "C": [0.00, 0.122, 0.40], "D": [0.125, 0.20, 0.125], "theta": [0, 0, 0]},
        {"id": "coffee_beans", "type": "object",
         "C": [0.00, 0.090, 0.40], "D": [0.100, 0.10, 0.100], "theta": [0, 0, 0]},

        # ---------- background ----------
        {"id": "coffee_grinder", "type": "object",
         "C": [0.26, 0.20, 0.30], "D": [0.21, 0.40, 0.22], "theta": [0, 0, 0]},
        {"id": "grinder_hopper", "type": "object",
         "C": [0.26, 0.50, 0.30], "D": [0.17, 0.20, 0.17], "theta": [0, 0, 0]},
        {"id": "plant_pot_right", "type": "object",
         "C": [0.70, 0.110, 0.26], "D": [0.19, 0.22, 0.19], "theta": [0, 0, 0]},
        {"id": "plant_right", "type": "object",
         "C": [0.70, 0.420, 0.26], "D": [0.50, 0.40, 0.34], "theta": [0, 0, 0]},

        # ---------- fixtures / structure ----------
        {"id": "countertop", "type": "object",
         "C": [0.05, -0.025, 0.37], "D": [2.90, 0.05, 0.70], "theta": [0, 0, 0]},
        {"id": "counter_cabinet", "type": "object",
         "C": [0.95, -0.47, 0.38], "D": [0.80, 0.82, 0.66], "theta": [0, 0, 0]},
        {"id": "backsplash", "type": "object",
         "C": [0.05, 0.26, 0.005], "D": [2.90, 0.52, 0.02], "theta": [0, 0, 0]},
        {"id": "wall_back", "type": "wall",
         "C": [0.05, 1.20, -0.08], "D": [2.90, 2.40, 0.16], "theta": [0, 0, 0]},
        {"id": "window_center", "type": "window",
         "C": [-0.15, 1.13, 0.00], "D": [0.95, 1.14, 0.10], "theta": [0, 0, 0]},
        {"id": "window_right", "type": "window",
         "C": [1.00, 1.13, 0.00], "D": [0.85, 1.14, 0.10], "theta": [0, 0, 0]},
    ]

    edges = [
        # embeds
        {"type": "embedded_in", "src": "window_center", "dst": "wall_back"},
        {"type": "embedded_in", "src": "window_right", "dst": "wall_back"},
        {"type": "overlaps_ok", "src": "backsplash", "dst": "wall_back"},

        # pour-over stack
        {"type": "abuts", "src": "digital_scale", "dst": "countertop"},
        {"type": "abuts", "src": "carafe", "dst": "digital_scale"},
        {"type": "abuts", "src": "dripper", "dst": "carafe"},
        {"type": "overlaps_ok", "src": "paper_filter", "dst": "dripper"},

        # beans on board
        {"type": "abuts", "src": "wooden_board", "dst": "countertop"},
        {"type": "abuts", "src": "glass_jar", "dst": "wooden_board"},
        {"type": "overlaps_ok", "src": "coffee_beans", "dst": "glass_jar"},

        # cup and saucer
        {"type": "abuts", "src": "saucer", "dst": "countertop"},
        {"type": "abuts", "src": "cup", "dst": "saucer"},
        {"type": "adjacent", "src": "saucer", "dst": "glass_jar"},

        # grinder
        {"type": "abuts", "src": "coffee_grinder", "dst": "countertop"},
        {"type": "abuts", "src": "grinder_hopper", "dst": "coffee_grinder"},
        {"type": "adjacent", "src": "coffee_grinder", "dst": "glass_jar"},

        # plants and their supports
        {"type": "abuts", "src": "wooden_block", "dst": "countertop"},
        {"type": "abuts", "src": "plant_pot_left", "dst": "wooden_block"},
        {"type": "abuts", "src": "plant_left", "dst": "plant_pot_left"},
        {"type": "abuts", "src": "plant_pot_right", "dst": "countertop"},
        {"type": "abuts", "src": "plant_right", "dst": "plant_pot_right"},

        # cloth and structure
        {"type": "abuts", "src": "cloth", "dst": "countertop"},
        {"type": "abuts", "src": "countertop", "dst": "counter_cabinet"},
        {"type": "adjacent", "src": "backsplash", "dst": "countertop"},
        {"type": "adjacent", "src": "plant_pot_right", "dst": "window_right"},
    ]

    return {"nodes": nodes, "edges": edges}

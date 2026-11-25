from __future__ import annotations


def build_scene_graph() -> dict:
    return {
        "nodes": [
    {
        "id": "floor",
        "type": "floor",
        "C": [
            2.5,
            -0.05,
            2.5
        ],
        "D": [
            5.0,
            0.1,
            5.0
        ],
        "theta": [
            0,
            0,
            0
        ]
    },
    {
        "id": "back_wall",
        "type": "wall",
        "C": [
            2.5,
            1.25,
            0.0
        ],
        "D": [
            5.0,
            2.5,
            0.16
        ],
        "theta": [
            0,
            0,
            0
        ]
    },
    {
        "id": "left_wall",
        "type": "wall",
        "C": [
            0.0,
            1.25,
            2.5
        ],
        "D": [
            5.0,
            2.5,
            0.16
        ],
        "theta": [
            0,
            90,
            0
        ]
    },
    {
        "id": "right_wall",
        "type": "wall",
        "C": [
            5.0,
            1.25,
            2.5
        ],
        "D": [
            5.0,
            2.5,
            0.16
        ],
        "theta": [
            0,
            -90,
            0
        ]
    },
    {
        "id": "front_wall",
        "type": "wall",
        "C": [
            2.5,
            1.25,
            5.0
        ],
        "D": [
            5.0,
            2.5,
            0.16
        ],
        "theta": [
            0,
            180,
            0
        ]
    },
    {
        "id": "chest_of_drawers",
        "type": "object",
        "C": [
            0.6,
            0.495,
            0.35
        ],
        "D": [
            1.0,
            0.99,
            0.537498
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                0.6,
                0.495,
                0.49
            ],
            "dims": [
                1.0,
                0.99,
                0.817498
            ]
        }
    },
    {
        "id": "desk",
        "type": "object",
        "C": [
            3.8,
            0.375,
            0.5
        ],
        "D": [
            1.4,
            0.75,
            0.6
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                3.8,
                0.375,
                0.616
            ],
            "dims": [
                1.4,
                0.75,
                0.832
            ]
        }
    },
    {
        "id": "coffee_table",
        "type": "object",
        "C": [
            2.0,
            0.2,
            2.5
        ],
        "D": [
            1.2,
            0.4,
            0.7
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                2.0,
                0.2,
                2.6355
            ],
            "dims": [
                1.2,
                0.4,
                0.971
            ]
        }
    },
    {
        "id": "wooden_chair",
        "type": "object",
        "C": [
            1.1,
            0.45,
            2.5
        ],
        "D": [
            0.476,
            0.9,
            0.476
        ],
        "theta": [
            0,
            90,
            0
        ],
        "swept_bbox": {
            "center": [
                1.1,
                0.45,
                2.5
            ],
            "dims": [
                0.476,
                0.9,
                0.476
            ]
        }
    },
    {
        "id": "floor_lamp",
        "type": "object",
        "C": [
            0.5,
            0.8469995,
            4.3
        ],
        "D": [
            0.304,
            1.693999,
            0.30109
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                0.5,
                0.864922,
                4.3
            ],
            "dims": [
                0.350452,
                1.729843,
                0.332327
            ]
        }
    },
    {
        "id": "desk_computer",
        "type": "object",
        "C": [
            3.8,
            1.0,
            0.4
        ],
        "D": [
            0.56,
            0.5,
            0.2
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                3.8,
                1.000518,
                0.4
            ],
            "dims": [
                0.56,
                0.501037,
                0.2
            ]
        }
    },
    {
        "id": "ceramic_mug",
        "type": "object",
        "C": [
            1.7,
            0.452,
            2.4
        ],
        "D": [
            0.1025,
            0.104,
            0.075976
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                1.7,
                0.452,
                2.4
            ],
            "dims": [
                0.1025,
                0.104,
                0.075976
            ]
        }
    },
    {
        "id": "glass_bottle",
        "type": "object",
        "C": [
            2.3,
            0.554,
            2.4
        ],
        "D": [
            0.0764,
            0.308,
            0.076376
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                2.3,
                0.5765,
                2.4
            ],
            "dims": [
                0.0764,
                0.353,
                0.076376
            ]
        }
    },
    {
        "id": "hardcover_book",
        "type": "object",
        "C": [
            2.0,
            0.43,
            2.6
        ],
        "D": [
            0.25,
            0.06,
            0.18
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                1.979483,
                0.43,
                2.6
            ],
            "dims": [
                0.291033,
                0.535169,
                0.18
            ]
        }
    },
    {
        "id": "flower_vase",
        "type": "object",
        "C": [
            0.6,
            1.1434,
            0.35
        ],
        "D": [
            0.165019,
            0.3068,
            0.159068
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                0.6,
                1.2034,
                0.35
            ],
            "dims": [
                0.165019,
                0.4268,
                0.159068
            ]
        }
    },
    {
        "id": "wall_clock",
        "type": "object",
        "C": [
            2.5,
            1.779944,
            0.08
        ],
        "D": [
            0.36,
            0.359888,
            0.0615
        ],
        "theta": [
            0,
            0,
            0
        ],
        "swept_bbox": {
            "center": [
                2.5,
                1.779944,
                0.08
            ],
            "dims": [
                0.36,
                0.359888,
                0.0615
            ]
        }
    }
],
        "edges": [
    {
        "type": "overlaps_ok",
        "src": "back_wall",
        "dst": "left_wall"
    },
    {
        "type": "overlaps_ok",
        "src": "back_wall",
        "dst": "right_wall"
    },
    {
        "type": "overlaps_ok",
        "src": "front_wall",
        "dst": "left_wall"
    },
    {
        "type": "overlaps_ok",
        "src": "front_wall",
        "dst": "right_wall"
    },
    {
        "type": "supports",
        "src": "desk_computer",
        "dst": "desk"
    },
    {
        "type": "supports",
        "src": "ceramic_mug",
        "dst": "coffee_table"
    },
    {
        "type": "supports",
        "src": "glass_bottle",
        "dst": "coffee_table"
    },
    {
        "type": "supports",
        "src": "hardcover_book",
        "dst": "coffee_table"
    },
    {
        "type": "supports",
        "src": "flower_vase",
        "dst": "chest_of_drawers"
    },
    {
        "type": "supports",
        "src": "wall_clock",
        "dst": "back_wall"
    },
    {
        "type": "overlaps_ok",
        "src": "desk_computer",
        "dst": "desk"
    },
    {
        "type": "overlaps_ok",
        "src": "ceramic_mug",
        "dst": "coffee_table"
    },
    {
        "type": "overlaps_ok",
        "src": "glass_bottle",
        "dst": "coffee_table"
    },
    {
        "type": "overlaps_ok",
        "src": "hardcover_book",
        "dst": "coffee_table"
    },
    {
        "type": "overlaps_ok",
        "src": "flower_vase",
        "dst": "chest_of_drawers"
    },
    {
        "type": "embedded_in",
        "src": "wall_clock",
        "dst": "back_wall"
    },
    {
        "type": "adjacent",
        "src": "chest_of_drawers",
        "dst": "back_wall"
    },
    {
        "type": "adjacent",
        "src": "desk",
        "dst": "back_wall"
    },
    {
        "type": "adjacent",
        "src": "wooden_chair",
        "dst": "coffee_table"
    }
],
    }

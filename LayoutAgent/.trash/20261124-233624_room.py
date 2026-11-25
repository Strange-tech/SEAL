from __future__ import annotations


def build_scene_graph() -> dict:
    return {
        "nodes": [
    {
        "id": "floor",
        "type": "floor",
        "C": [
            2.0,
            -0.05,
            2.0
        ],
        "D": [
            4.0,
            0.1,
            4.0
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
            2.0,
            1.2,
            0.0
        ],
        "D": [
            4.0,
            2.4,
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
            1.2,
            2.0
        ],
        "D": [
            4.0,
            2.4,
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
            4.0,
            1.2,
            2.0
        ],
        "D": [
            4.0,
            2.4,
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
            2.0,
            1.2,
            4.0
        ],
        "D": [
            4.0,
            2.4,
            0.16
        ],
        "theta": [
            0,
            180,
            0
        ]
    },
    {
        "id": "coffee_table",
        "type": "object",
        "class": "round coffee table",
        "C": [
            1.8,
            0.2,
            1.8
        ],
        "D": [
            1.2,
            0.4,
            0.6
        ],
        "theta": [
            0,
            0,
            0
        ],
        "real_bbox": {
            "center": [
                1.8,
                0.2,
                1.8
            ],
            "dims": [
                1.2,
                0.4,
                0.6
            ]
        }
    },
    {
        "id": "wooden_chair",
        "type": "object",
        "class": "wooden chair",
        "C": [
            1.25,
            0.45,
            2.1
        ],
        "D": [
            0.45,
            0.9,
            0.44
        ],
        "theta": [
            0,
            118,
            0
        ],
        "real_bbox": {
            "center": [
                1.25,
                0.45,
                2.1
            ],
            "dims": [
                0.45,
                0.9,
                0.44
            ]
        }
    },
    {
        "id": "chest_of_drawers",
        "type": "object",
        "class": "chest of drawers",
        "C": [
            3.2,
            0.4,
            0.35
        ],
        "D": [
            0.9,
            0.8,
            0.502498
        ],
        "theta": [
            0,
            0,
            0
        ],
        "real_bbox": {
            "center": [
                3.2,
                0.4,
                0.5
            ],
            "dims": [
                0.9,
                0.8,
                0.802498
            ]
        }
    },
    {
        "id": "floor_lamp",
        "type": "object",
        "class": "floor lamp",
        "C": [
            0.5,
            0.80838,
            0.7
        ],
        "D": [
            0.304,
            1.616759,
            0.770992
        ],
        "theta": [
            0,
            0,
            0
        ],
        "real_bbox": {
            "center": [
                0.5,
                0.926937,
                0.749206
            ],
            "dims": [
                0.304,
                1.853873,
                0.869404
            ]
        }
    },
    {
        "id": "hardcover_book",
        "type": "object",
        "class": "hardcover book",
        "C": [
            1.7,
            0.415,
            1.7
        ],
        "D": [
            0.23,
            0.03,
            0.157
        ],
        "theta": [
            0,
            20,
            0
        ],
        "real_bbox": {
            "center": [
                1.673931,
                0.491942,
                1.628376
            ],
            "dims": [
                0.23,
                0.183883,
                0.309442
            ]
        }
    },
    {
        "id": "ceramic_mug",
        "type": "object",
        "class": "ceramic mug",
        "C": [
            1.95,
            0.4475,
            1.75
        ],
        "D": [
            0.120416,
            0.095,
            0.085
        ],
        "theta": [
            0,
            0,
            0
        ],
        "real_bbox": {
            "center": [
                1.95,
                0.4475,
                1.75
            ],
            "dims": [
                0.120416,
                0.095,
                0.085
            ]
        }
    },
    {
        "id": "glass_bottle",
        "type": "object",
        "class": "glass bottle",
        "C": [
            2.0,
            0.5545,
            1.65
        ],
        "D": [
            0.076482,
            0.309,
            0.076484
        ],
        "theta": [
            0,
            0,
            0
        ],
        "real_bbox": {
            "center": [
                2.0,
                0.572,
                1.65
            ],
            "dims": [
                0.076482,
                0.344,
                0.076484
            ]
        }
    },
    {
        "id": "flower_vase",
        "type": "object",
        "class": "flower vase",
        "C": [
            3.15,
            0.925,
            0.35
        ],
        "D": [
            0.120062,
            0.25,
            0.12006
        ],
        "theta": [
            0,
            0,
            0
        ],
        "real_bbox": {
            "center": [
                3.15,
                0.925,
                0.35
            ],
            "dims": [
                0.120062,
                0.25,
                0.12006
            ]
        }
    },
    {
        "id": "desk_lamp",
        "type": "object",
        "class": "desk lamp",
        "C": [
            3.55,
            0.977434,
            0.35
        ],
        "D": [
            0.143996,
            0.354868,
            0.396977
        ],
        "theta": [
            0,
            0,
            0
        ],
        "real_bbox": {
            "center": [
                3.55,
                0.979311,
                0.366977
            ],
            "dims": [
                0.143996,
                0.664156,
                0.741435
            ]
        }
    },
    {
        "id": "wall_clock",
        "type": "object",
        "class": "wall clock",
        "C": [
            2.0,
            1.79,
            0.11
        ],
        "D": [
            0.299906,
            0.3,
            0.052
        ],
        "theta": [
            0,
            0,
            0
        ],
        "real_bbox": {
            "center": [
                2.0,
                1.79,
                0.11
            ],
            "dims": [
                0.299906,
                0.3,
                0.052
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
        "type": "overlaps_ok",
        "src": "wooden_chair",
        "dst": "coffee_table"
    },
    {
        "type": "supports",
        "src": "hardcover_book",
        "dst": "coffee_table"
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
        "src": "flower_vase",
        "dst": "chest_of_drawers"
    },
    {
        "type": "supports",
        "src": "desk_lamp",
        "dst": "chest_of_drawers"
    },
    {
        "type": "supports",
        "src": "wall_clock",
        "dst": "back_wall"
    },
    {
        "type": "overlaps_ok",
        "src": "hardcover_book",
        "dst": "coffee_table"
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
        "src": "flower_vase",
        "dst": "chest_of_drawers"
    },
    {
        "type": "overlaps_ok",
        "src": "desk_lamp",
        "dst": "chest_of_drawers"
    },
    {
        "type": "overlaps_ok",
        "src": "wall_clock",
        "dst": "back_wall"
    },
    {
        "type": "adjacent",
        "src": "chest_of_drawers",
        "dst": "back_wall"
    }
],
    }

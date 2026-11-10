"""Validation layer tests (run directly: python layoutagent/tests/test_validation.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema
from sdk.validation import validate_scene_graph


def make_room():
    g = schema.new_scene_graph()
    g["nodes"] = [
        schema.make_node("floor", "floor", [0, -0.05, 0], [6, 0.1, 5], [0, 0, 0]),
        schema.make_node("wall_0", "wall", [0, 1.5, -2], [5, 3, 0.16], [0, 0, 0]),
        schema.make_node("table_0", "object", [0, 0.375, 0.5], [1.2, 0.75, 0.8], [0, 0, 0]),
        schema.make_node("chair_0", "object", [0, 0.225, 0.5], [0.45, 0.45, 0.45], [0, 0, 0]),
    ]
    g["edges"] = [schema.make_edge("overlaps_ok", "chair_0", "table_0")]
    return g


def test_valid_room():
    f, w, n = validate_scene_graph(make_room())
    assert f == [], f
    print("[ok] valid room: no failures")


def test_collision():
    g = make_room()
    g["nodes"].append(schema.make_node("box_0", "object", [0.5, 0.2, 0.5], [0.5, 0.4, 0.5], [0, 0, 0]))
    f, w, n = validate_scene_graph(g)
    assert any("collision" in x for x in f), f
    print("[ok] collision detected")


def test_floating():
    g = make_room()
    g["nodes"].append(schema.make_node("lamp_0", "object", [0, 2.0, 0], [0.3, 0.3, 0.3], [0, 0, 0]))
    f, w, n = validate_scene_graph(g)
    assert any("floating" in x for x in f), f
    print("[ok] floating detected")


def test_embedded_exempt():
    g = make_room()
    g["nodes"].append(schema.make_node("door_0", "door", [0, 1.0, -2], [0.9, 2.0, 0.16], [0, 0, 0]))
    g["edges"].append(schema.make_edge("embedded_in", "door_0", "wall_0"))
    f, w, n = validate_scene_graph(g)
    assert not any("collision" in x for x in f), f
    print("[ok] embedded_in exempts door-wall collision")


def test_overlaps_ok_warning():
    g = make_room()
    # declares overlaps_ok but the two objects do not actually intersect -> warning
    g["edges"].append(schema.make_edge("overlaps_ok", "wall_0", "table_0"))
    f, w, n = validate_scene_graph(g)
    assert any("no overlap" in x for x in w), (f, w)
    print("[ok] overlaps_ok with no overlap raises warning")


def test_bad_structure():
    g = make_room()
    g["edges"].append(schema.make_edge("adjacent", "ghost", "table_0"))
    f, w, n = validate_scene_graph(g)
    assert any("unknown node" in x for x in f), f
    print("[ok] structure error detected")


if __name__ == "__main__":
    test_valid_room()
    test_collision()
    test_floating()
    test_embedded_exempt()
    test_overlaps_ok_warning()
    test_bad_structure()
    print("\nALL VALIDATION TESTS PASSED")

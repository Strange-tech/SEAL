"""compile tool tests (run directly: python layoutagent/tests/test_compile.py)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.compile import compile_layout, load_scene_graph, format_diagnostics

VALID = '''
def build_scene_graph():
    return {
        "nodes": [
            {"id": "floor", "type": "floor", "C": [0, -0.05, 0], "D": [6, 0.1, 5], "theta": [0, 0, 0]},
            {"id": "wall_0", "type": "wall", "C": [0, 1.5, -2], "D": [5, 3, 0.16], "theta": [0, 0, 0]},
            {"id": "table_0", "type": "object", "C": [0, 0.375, 0.5], "D": [1.2, 0.75, 0.8], "theta": [0, 0, 0]},
        ],
        "edges": [],
    }
'''

COLLISION = '''
def build_scene_graph():
    return {
        "nodes": [
            {"id": "floor", "type": "floor", "C": [0, -0.05, 0], "D": [6, 0.1, 5], "theta": [0, 0, 0]},
            {"id": "table_0", "type": "object", "C": [0, 0.375, 0.5], "D": [1.2, 0.75, 0.8], "theta": [0, 0, 0]},
            {"id": "box_0", "type": "object", "C": [0.5, 0.2, 0.5], "D": [0.5, 0.4, 0.5], "theta": [0, 0, 0]},
        ],
        "edges": [],
    }
'''

SYNTAX_ERROR = '''
def build_scene_graph(
    return {}
'''


def _write(tmp, content):
    p = os.path.join(tmp, "room.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def test_valid():
    with tempfile.TemporaryDirectory() as d:
        p = _write(d, VALID)
        graph, failures, warnings, notes = compile_layout(p)
        assert failures == [], failures
        assert graph is not None and len(graph["nodes"]) == 3
        text = format_diagnostics(failures, warnings, notes)
        assert "[ok]" in text
    print("[ok] compile valid layout")


def test_collision():
    with tempfile.TemporaryDirectory() as d:
        p = _write(d, COLLISION)
        graph, failures, warnings, notes = compile_layout(p)
        assert any("collision" in f for f in failures), failures
    print("[ok] compile detects collision")


def test_syntax_error():
    with tempfile.TemporaryDirectory() as d:
        p = _write(d, SYNTAX_ERROR)
        graph, failures, warnings, notes = compile_layout(p)
        assert graph is None
        assert failures and any("Error executing room.py" in f for f in failures), failures
    print("[ok] compile reports syntax error")


def test_load_missing_contract():
    with tempfile.TemporaryDirectory() as d:
        p = _write(d, "x = 1\n")
        graph, error = load_scene_graph(p)
        assert graph is None
        assert "build_scene_graph" in error
    print("[ok] load_scene_graph missing contract")


if __name__ == "__main__":
    test_valid()
    test_collision()
    test_syntax_error()
    test_load_missing_contract()
    print("\nALL COMPILE TESTS PASSED")

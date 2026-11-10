"""
Model-file top-level contract, ported verbatim from the official Articraft
`agent/tools/model_contract.py`.

The generated `model.py` must always expose a fixed top-level surface so the
compiler can locate and drive it:

    def build_object_model() -> ArticulatedObject: ...
    def run_tests() -> TestReport: ...
    object_model = build_object_model()

`missing_required_model_contract` returns the pieces that are absent (or an
empty list when the contract is satisfied). Syntax errors are intentionally
NOT reported here — they are surfaced separately with richer line details by
the syntax validator in the edit/write tools.
"""

from __future__ import annotations

import ast


def missing_required_model_contract(model_code: str) -> list[str]:
    try:
        tree = ast.parse(model_code)
    except SyntaxError:
        # Let syntax validation surface this with richer line details.
        return []

    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = [name for name in ("build_object_model", "run_tests") if name not in defined]
    if not _has_object_model_assignment(tree):
        missing.append("object_model = build_object_model()")
    return missing


def _has_object_model_assignment(tree: ast.Module) -> bool:
    for node in tree.body:
        value: ast.AST | None = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]

        if not isinstance(value, ast.Call):
            continue
        if not isinstance(value.func, ast.Name) or value.func.id != "build_object_model":
            continue
        if any(isinstance(target, ast.Name) and target.id == "object_model" for target in targets):
            return True
    return False

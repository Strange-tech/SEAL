"""Run all tests in one go: python layoutagent/tests/run_all.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST_NAMES = [
    "geometry", "validation", "manhattan", "projection",
    "fitting", "compile",
]


def main():
    passed = failed = 0
    for name in TEST_NAMES:
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, f"test_{name}.py")],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            print(f"[pass] {name}")
            passed += 1
        else:
            print(f"[FAIL] {name}")
            print(r.stdout)
            print(r.stderr)
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

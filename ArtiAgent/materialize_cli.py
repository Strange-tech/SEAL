from __future__ import annotations

import shutil
import sys
from pathlib import Path

from agent.persistence import materialize_record
from storage.materialize import build_materialization_summary, materialization_paths
from storage.repo import StorageRepo


def print_help() -> None:
    print("Usage: python materialize_cli.py --record_id <record_id> [--output <dir>]")
    print("")
    print("Recompile a record's active model.py into its materialization dir, then")
    print("optionally export model.urdf + meshes to <dir> (created if missing).")


def _parse_args(argv: list[str]) -> tuple[str | None, str | None]:
    record_id: str | None = None
    output_dir: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--record_id":
            if i + 1 >= len(argv):
                print("Usage: --record_id <record_id>", file=sys.stderr)
                sys.exit(1)
            record_id = argv[i + 1]
            i += 2
            continue
        if a in ("--output", "-o"):
            if i + 1 >= len(argv):
                print("Usage: --output <dir>", file=sys.stderr)
                sys.exit(1)
            output_dir = argv[i + 1]
            i += 2
            continue
        if a.startswith("--record_id="):
            record_id = a.split("=", 1)[1]
        elif a.startswith("--output="):
            output_dir = a.split("=", 1)[1]
        elif a.startswith("-o="):
            output_dir = a.split("=", 1)[1]
        elif a in ("-h", "--help"):
            print_help()
            sys.exit(0)
        else:
            print(f"Unexpected argument: {a} (use --record_id <record_id>)", file=sys.stderr)
            sys.exit(1)
        i += 1
    return record_id, output_dir


def export_materialization(urdf_path: Path, meshes_dir: Path, out: Path) -> None:
    """Copy model.urdf + meshes into `out`, preserving the assets/meshes/ layout
    so the URDF's relative mesh references keep resolving. CadQuery `.cadquery.json`
    sidecars are not meshes and are skipped."""
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(urdf_path, out / "model.urdf")
    copied = ["model.urdf"]

    mesh_files: list[Path] = []
    if meshes_dir.is_dir():
        mesh_files = [
            p for p in meshes_dir.iterdir()
            if p.is_file() and not p.name.endswith(".cadquery.json")
        ]
    if mesh_files:
        dest = out / "assets" / "meshes"
        dest.mkdir(parents=True, exist_ok=True)
        for p in mesh_files:
            shutil.copy2(p, dest / p.name)
        copied.append(f"assets/meshes/ ({len(mesh_files)} meshes)")
    else:
        copied.append("assets/meshes/ (none)")

    print("exported  ->", out.resolve())
    for item in copied:
        print("  " + item)


def main(record_id: str, output_dir: str | None = None) -> None:
    repo_root = Path(__file__).resolve().parent
    urdf_path, warnings, status = materialize_record(repo_root, record_id, sdk_package="sdk")

    sr = StorageRepo(repo_root)
    paths = materialization_paths(sr, record_id)
    summary = build_materialization_summary(sr, record_id)

    print("record_id ->", record_id)
    print("status    ->", status)
    print("urdf      ->", urdf_path.resolve())
    print("meshes    ->", paths["meshes_dir"].resolve())
    print("summary   ->", summary)
    if warnings:
        print("warnings  ->", warnings)

    if output_dir:
        export_materialization(urdf_path, paths["meshes_dir"], Path(output_dir))


if __name__ == "__main__":
    if not sys.argv[1:]:
        print_help()
        sys.exit(1)
    record_id, output_dir = _parse_args(sys.argv[1:])
    if not record_id:
        print_help()
        sys.exit(1)
    try:
        main(record_id, output_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

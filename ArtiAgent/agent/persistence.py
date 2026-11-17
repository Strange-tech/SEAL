"""
Wire a finished agent run into the ported `storage` layer.

This is a minimal, synchronous mirror of the official Articraft
`agent/run_context.py` + `agent/record_persistence.py` + `storage/materialize.py`
wiring: one run -> one record (revision + provenance + lineage) -> one materialization.

The reimplementation has no async run/orchestration stack, so these helpers stay
small and take plain keyword arguments from `main.py`.
"""

from __future__ import annotations

import hashlib
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.compiler import compile_urdf_report_maybe_timeout
from storage.library_manifest import upsert_record
from storage.materialize import MaterializationStore
from storage.models import (
    CompileWarning,
    DisplayMetadata,
    EnvironmentSettings,
    GenerationSettings,
    PromptingSettings,
    Provenance,
    Record,
    RecordArtifacts,
    RecordHashes,
    RunSummary,
    SdkSettings,
    SourceRef,
)
from storage.models import CompileReport as StorageCompileReport
from storage.records import RecordStore
from storage.repo import StorageRepo
from storage.revisions import (
    INITIAL_REVISION_ID,
    active_model_path,
    build_revision_payload,
    revision_artifacts_payload,
)

INITIAL_REVISION_ID = INITIAL_REVISION_ID  # re-export for callers


def _slugify(text: str) -> str:
    cleaned: list[str] = []
    last_dash = False
    for ch in text.lower():
        if ch.isalnum():
            cleaned.append(ch)
            last_dash = False
        elif not last_dash:
            cleaned.append("-")
            last_dash = True
    slug = "".join(cleaned).strip("-")
    return slug or "object"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _prompt_preview(prompt: str, *, max_len: int = 160) -> str:
    collapsed = " ".join(prompt.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3].rstrip() + "..."


def _display_title(prompt: str, *, label: str | None = None) -> str:
    if label and label.strip():
        return label.strip()
    first_line = next((line.strip() for line in prompt.splitlines() if line.strip()), "")
    return first_line[:120] if first_line else "Untitled run"


def _platform_id() -> str:
    return f"{platform.system().lower()}-{platform.machine().lower()}"


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_record_id(prompt: str) -> str:
    """Derive a `rec_...` id the same way the official `_build_single_run_context` does."""
    slug = _slugify(prompt)[:48]
    token = _timestamp_token()
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
    return f"rec_{slug}_{token}_{digest}"


def active_model_text(repo_root: Path, record_id: str) -> str | None:
    """Return the active `model.py` text of an existing record (for `--edit`)."""
    sr = StorageRepo(Path(repo_root).resolve())
    path = active_model_path(sr, record_id)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def active_lineage(repo_root: Path, record_id: str) -> dict | None:
    """Return the lineage dict of an existing record (for `--edit`)."""
    sr = StorageRepo(Path(repo_root).resolve())
    record = sr.read_json(sr.layout.record_metadata_path(record_id), default=None)
    if not isinstance(record, dict):
        return None
    lineage = record.get("lineage")
    return dict(lineage) if isinstance(lineage, dict) else None


def fork_context(repo_root: Path, record_id: str) -> tuple[str | None, dict | None]:
    """Return ``(parent_model_text, lineage)`` for forking an existing record.

    The lineage chain preserves the parent's ``origin_record_id`` (so descendants can
    trace back to the very first ancestor) and points ``parent_*`` at the forked record.
    """
    sr = StorageRepo(Path(repo_root).resolve())
    record = sr.read_json(sr.layout.record_metadata_path(record_id), default=None)
    if not isinstance(record, dict):
        return None, None
    model_text = active_model_text(repo_root, record_id)
    if model_text is None:
        return None, None
    active_rev = str(record.get("active_revision_id") or INITIAL_REVISION_ID)
    parent_lineage = record.get("lineage")
    parent_lineage = dict(parent_lineage) if isinstance(parent_lineage, dict) else {}
    origin = str(parent_lineage.get("origin_record_id") or record_id)
    return model_text, {
        "origin_record_id": origin,
        "parent_record_id": record_id,
        "parent_revision_id": active_rev,
        "edit_mode": "copy",
    }


def materialize_record(
    repo_root: Path,
    record_id: str,
    *,
    sdk_package: str = "sdk",
) -> tuple[Path, list[str], str]:
    """Compile a record's active `model.py` into the storage materialization dir.

    Returns ``(urdf_path, warnings, status)``. Meshes land under
    ``<materialization>/assets/meshes/`` (the SDK default mesh subdir), matching the
    official layout; the URDF is written next to them at ``<materialization>/model.urdf``.
    """
    sr = StorageRepo(Path(repo_root).resolve())
    sr.ensure_layout()
    mats = MaterializationStore(sr)

    model_path = active_model_path(sr, record_id)
    if not model_path.is_file():
        raise FileNotFoundError(f"Record {record_id} has no active model.py: {model_path}")

    materialization_dir = sr.layout.record_materialization_dir(record_id)
    urdf_xml = ""
    warnings: list[str] = []
    status = "success"
    try:
        report = compile_urdf_report_maybe_timeout(
            model_path,
            sdk_package=sdk_package,
            run_checks=False,
            rewrite_visual_glb=False,
            asset_root=materialization_dir,
        )
        urdf_xml = report.urdf_xml or ""
        warnings = list(report.warnings or [])
    except Exception as exc:  # keep the record even when the final compile breaks
        warnings = [f"compile failed: {exc}"]
        status = "failed"

    urdf_path = sr.layout.record_materialization_urdf_path(record_id)
    sr.write_text(urdf_path, urdf_xml)
    mats.write_compile_report(
        record_id,
        StorageCompileReport(
            schema_version=1,
            record_id=record_id,
            status=status,
            urdf_path="model.urdf",
            warnings=[CompileWarning(code="warning", message=w) for w in warnings],
            checks_run=["compile_urdf"],
            metrics={},
        ),
    )
    return urdf_path, warnings, status


def write_success_record(
    *,
    repo_root: Path,
    prompt: str,
    provider: str,
    model_id: str,
    sdk_package: str = "sdk",
    image_path: str | None = None,
    max_turns: int | None = None,
    thinking_level: str = "high",
    label: str | None = None,
    tags: list[str] | None = None,
    record_id: str | None = None,
    lineage: dict | None = None,
    turn_count: int = 0,
    tool_call_count: int = 0,
    compile_attempt_count: int = 0,
    system_prompt_name: str = "designer_system_prompt_deepseek.txt",
) -> tuple[str, Path]:
    """Persist one finished run as a record (source + revision + provenance + manifest),
    then materialize it (URDF + meshes + compile report).

    Returns ``(record_id, record_dir)``.
    """
    repo_root = Path(repo_root).resolve()
    sr = StorageRepo(repo_root)
    sr.ensure_layout()
    store = RecordStore(sr)

    record_id = record_id or new_record_id(prompt)
    revision_id = INITIAL_REVISION_ID
    created_at = _utc_now()

    model_path = Path("model.py")
    if not model_path.is_file():
        raise FileNotFoundError(f"Missing model.py to record: {model_path}")
    model_text = model_path.read_text(encoding="utf-8", errors="replace")

    if lineage is None:
        lineage = {
            "origin_record_id": record_id,
            "parent_record_id": None,
            "parent_revision_id": None,
            "edit_mode": "root",
        }
    parent_record_id = lineage.get("parent_record_id")
    parent_revision_id = lineage.get("parent_revision_id")
    revision_parent = (
        {"record_id": parent_record_id, "revision_id": parent_revision_id}
        if parent_record_id and parent_revision_id
        else None
    )

    # 1) source-of-truth files in the record's initial revision dir
    sr.write_text(sr.layout.record_revision_model_path(record_id, revision_id), model_text)
    sr.write_text(sr.layout.record_revision_prompt_path(record_id, revision_id), prompt)
    if image_path is not None:
        store.copy_input_image(
            record_id, Path(image_path), missing_ok=True, revision_id=revision_id
        )

    # 2) provenance (how this revision was produced)
    generation = GenerationSettings(
        provider=provider,
        model_id=model_id,
        thinking_level=thinking_level,
        max_turns=max_turns,
    )
    run_summary = RunSummary(
        turn_count=turn_count,
        tool_call_count=tool_call_count,
        compile_attempt_count=compile_attempt_count,
        final_status="success",
    )
    store.write_provenance(
        record_id,
        Provenance(
            schema_version=2,
            record_id=record_id,
            generation=generation,
            prompting=PromptingSettings(
                system_prompt_file=system_prompt_name, system_prompt_sha256=None
            ),
            sdk=SdkSettings(sdk_package=sdk_package, sdk_version="workspace", sdk_fingerprint=None),
            environment=EnvironmentSettings(
                python_version=_python_version(), platform=_platform_id()
            ),
            run_summary=run_summary,
        ),
        revision_id=revision_id,
    )

    # 3) revision metadata
    prompt_sha = _sha256_text(prompt)
    model_py_sha = _sha256_file(model_path)
    sr.write_json(
        sr.layout.record_revision_metadata_path(record_id, revision_id),
        build_revision_payload(
            record_id=record_id,
            revision_id=revision_id,
            created_at=created_at,
            prompt_text=prompt,
            prompt_kind="single_prompt",
            source={"run_id": None, "prompt_index": None},
            generation=generation.to_dict(),
            artifacts=revision_artifacts_payload(
                revision_id=revision_id, has_cost_file=False
            ),
            hashes={"prompt_sha256": prompt_sha, "model_py_sha256": model_py_sha},
            run_summary=run_summary.to_dict(),
            parent=revision_parent,
        ),
    )

    # 4) record.json (the library-level object)
    store.write_record(
        Record(
            schema_version=3,
            record_id=record_id,
            created_at=created_at,
            updated_at=_utc_now(),
            rating=None,
            kind="generated_model",
            prompt_kind="single_prompt",
            category_slug=None,
            source=SourceRef(run_id=None),
            sdk_package=sdk_package,
            provider=provider,
            model_id=model_id,
            display=DisplayMetadata(
                title=_display_title(prompt, label=label), prompt_preview=_prompt_preview(prompt)
            ),
            artifacts=RecordArtifacts(
                prompt_txt=revision_artifacts_payload(
                    revision_id=revision_id, has_cost_file=False
                )["prompt_txt"],
                prompt_series_json=None,
                model_py=revision_artifacts_payload(
                    revision_id=revision_id, has_cost_file=False
                )["model_py"],
                provenance_json=revision_artifacts_payload(
                    revision_id=revision_id, has_cost_file=False
                )["provenance_json"],
                cost_json=None,
            ),
            hashes=RecordHashes(prompt_sha256=prompt_sha, model_py_sha256=model_py_sha),
            active_revision_id=revision_id,
            lineage=lineage,
            label=label,
            tags=list(tags or []),
        )
    )

    # 5) materialize (URDF + meshes + compile report) and update the manifest
    materialize_record(repo_root, record_id, sdk_package=sdk_package)
    upsert_record(sr, record_id)

    return record_id, sr.layout.record_dir(record_id)

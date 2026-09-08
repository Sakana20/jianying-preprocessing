from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .draft import load_draft, validate_references
from .errors import ApplyError, RollbackError
from .planner import build_plan
from .util import canonical_json_bytes, file_mode, fsync_directory, read_json, sha256_file


def _write_atomic(path: Path, data: bytes, mode: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verify_saved_plan(saved: dict[str, Any], current: dict[str, Any]) -> None:
    required = {
        "plan_schema",
        "plan_id",
        "job_sha256",
        "draft_path",
        "base_hashes",
        "component_hashes",
        "config_set_id",
        "changes",
    }
    missing = required - saved.keys()
    if missing:
        raise ApplyError(f"saved plan is missing fields: {', '.join(sorted(missing))}")
    for key in required:
        if saved.get(key) != current.get(key):
            raise ApplyError(f"saved plan is stale or mismatched at {key}")


def _jianying_running() -> bool:
    if sys.platform != "darwin":
        return False
    result = subprocess.run(
        ["pgrep", "-f", r"com\.lemon\.lvpro|VideoFusion-macOS|/剪映专业版(?:-|\.app|$)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise ApplyError("cannot determine whether JianYing is running; refusing to write the Draft")


def apply_plan(job_path: Path, plan_path: Path) -> dict[str, Any]:
    try:
        saved_plan = read_json(plan_path.expanduser().resolve())
    except (OSError, ValueError) as exc:
        raise ApplyError(f"cannot read saved plan: {exc}") from exc
    build = build_plan(job_path, require_approved=True)
    _verify_saved_plan(saved_plan, build.plan)
    if _jianying_running():
        raise ApplyError("JianYing is running; close it before applying a multi-file Draft transaction")
    if build.plan["no_op"]:
        return {"applied": False, "no_op": True, "plan_id": build.plan["plan_id"], "files": []}
    draft_path = Path(build.plan["draft_path"])
    run_id = f"{build.plan['plan_id'][:12]}-{uuid.uuid4().hex[:8]}"
    backup_dir = draft_path / ".jypre" / "backups" / run_id
    backup_dir.mkdir(parents=True)
    changed_files = [
        *[name for name in build.plan["changes"]["files"] if name != ".jypre/state.json"],
        *([".jypre/state.json"] if ".jypre/state.json" in build.plan["changes"]["files"] else []),
    ]
    manifest: dict[str, Any] = {
        "manifest_schema": 1,
        "run_id": run_id,
        "plan_id": build.plan["plan_id"],
        "draft_path": str(draft_path),
        "files": {},
        "applied_hashes": {},
    }
    try:
        for name in changed_files:
            target = draft_path / name
            if target.is_file():
                backup_target = backup_dir / name
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup_target)
                manifest["files"][name] = {"existed": True, "mode": file_mode(target), "sha256": sha256_file(target)}
            else:
                manifest["files"][name] = {"existed": False, "mode": None, "sha256": None}
        _write_atomic(backup_dir / "manifest.json", canonical_json_bytes(manifest), 0o600)
        for name in changed_files:
            target = draft_path / name
            prior = manifest["files"][name]
            document = build.desired.documents[name]
            _write_atomic(target, canonical_json_bytes(document), prior["mode"] or 0o600)
            manifest["applied_hashes"][name] = sha256_file(target)
        reloaded = load_draft(draft_path)
        validation = validate_references(reloaded.info)
        if not validation["valid"]:
            raise ApplyError("post-write validation failed: " + "; ".join(validation["errors"]))
        for name, expected in build.plan["changes"]["target_hashes"].items():
            actual = sha256_file(draft_path / name)
            if actual != expected:
                raise ApplyError(f"post-write hash mismatch for {name}: expected {expected}, got {actual}")
        _write_atomic(backup_dir / "manifest.json", canonical_json_bytes(manifest), 0o600)
    except Exception as exc:
        try:
            _restore_from_manifest(draft_path, backup_dir, manifest, check_current=False)
        except Exception as rollback_exc:
            raise ApplyError(f"apply failed ({exc}); automatic rollback also failed ({rollback_exc})") from exc
        if isinstance(exc, ApplyError):
            raise
        raise ApplyError(f"apply failed and was rolled back: {exc}") from exc
    return {
        "applied": True,
        "no_op": False,
        "plan_id": build.plan["plan_id"],
        "run_id": run_id,
        "files": changed_files,
        "backup_dir": str(backup_dir),
    }


def _restore_from_manifest(
    draft_path: Path, backup_dir: Path, manifest: dict[str, Any], *, check_current: bool
) -> list[str]:
    restored = []
    for name, record in manifest["files"].items():
        target = draft_path / name
        if check_current and target.is_file():
            expected = manifest.get("applied_hashes", {}).get(name)
            if expected and sha256_file(target) != expected:
                raise RollbackError(f"{name} changed after apply; refusing destructive rollback")
        if record["existed"]:
            source = backup_dir / name
            if not source.is_file() or sha256_file(source) != record["sha256"]:
                raise RollbackError(f"backup is missing or corrupt for {name}")
            _write_atomic(target, source.read_bytes(), record["mode"])
        elif target.exists():
            target.unlink()
            fsync_directory(target.parent)
        restored.append(name)
    return restored


def rollback(draft_path: Path, run_id: str) -> dict[str, Any]:
    resolved = draft_path.expanduser().resolve()
    backup_dir = resolved / ".jypre" / "backups" / run_id
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RollbackError(f"rollback manifest does not exist: {manifest_path}")
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError) as exc:
        raise RollbackError(f"cannot read rollback manifest: {exc}") from exc
    if manifest.get("draft_path") != str(resolved) or manifest.get("run_id") != run_id:
        raise RollbackError("rollback manifest target or run ID mismatch")
    restored = _restore_from_manifest(resolved, backup_dir, manifest, check_current=True)
    return {"rolled_back": True, "run_id": run_id, "files": restored, "backup_retained": True}

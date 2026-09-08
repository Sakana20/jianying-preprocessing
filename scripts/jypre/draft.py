from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DraftError
from .util import read_json, sha256_file

DRAFT_FILES = (
    "draft_info.json",
    "draft_meta_info.json",
    "key_value.json",
    "draft_virtual_store.json",
    "template-2.tmp",
)


@dataclass
class DraftBundle:
    path: Path
    documents: dict[str, Any]
    hashes: dict[str, str | None]

    @property
    def info(self) -> dict[str, Any]:
        return self.documents["draft_info.json"]

    @property
    def state_path(self) -> Path:
        return self.path / ".jypre" / "state.json"

    @property
    def state(self) -> dict[str, Any] | None:
        return self.documents.get(".jypre/state.json")

    def clone(self) -> DraftBundle:
        return DraftBundle(self.path, copy.deepcopy(self.documents), dict(self.hashes))


def load_draft(path: Path) -> DraftBundle:
    draft_path = path.expanduser().resolve()
    if not draft_path.is_dir():
        raise DraftError(f"draft directory does not exist: {draft_path}")
    info_path = draft_path / "draft_info.json"
    if not info_path.is_file():
        raise DraftError(f"draft_info.json does not exist: {info_path}")
    documents: dict[str, Any] = {}
    hashes: dict[str, str | None] = {}
    for name in DRAFT_FILES:
        candidate = draft_path / name
        if candidate.is_file():
            try:
                documents[name] = read_json(candidate)
                hashes[name] = sha256_file(candidate)
            except (OSError, ValueError) as exc:
                raise DraftError(f"cannot read {name}: {exc}") from exc
        else:
            hashes[name] = None
    state_path = draft_path / ".jypre" / "state.json"
    if state_path.is_file():
        try:
            documents[".jypre/state.json"] = read_json(state_path)
            hashes[".jypre/state.json"] = sha256_file(state_path)
        except (OSError, ValueError) as exc:
            raise DraftError(f"cannot read .jypre/state.json: {exc}") from exc
    else:
        hashes[".jypre/state.json"] = None
    return DraftBundle(draft_path, documents, hashes)


def material_index(info: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    duplicates: list[str] = []
    for kind, items in info.get("materials", {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            item_id = item["id"]
            if item_id in result:
                duplicates.append(item_id)
            result[item_id] = (kind, item)
    if duplicates:
        raise DraftError(f"duplicate material IDs: {', '.join(sorted(set(duplicates)))}")
    return result


def iter_segments(info: dict[str, Any]) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    for track in info.get("tracks", []):
        if not isinstance(track, dict):
            continue
        for segment in track.get("segments", []):
            if isinstance(segment, dict):
                yield track, segment


def validate_references(info: dict[str, Any]) -> dict[str, Any]:
    materials = material_index(info)
    segment_ids: set[str] = set()
    duplicate_segments: set[str] = set()
    dangling_materials: list[str] = []
    dangling_extra: list[str] = []
    invalid_ranges: list[str] = []
    max_end = 0
    for _track, segment in iter_segments(info):
        segment_id = segment.get("id", "<missing>")
        if segment_id in segment_ids:
            duplicate_segments.add(str(segment_id))
        segment_ids.add(str(segment_id))
        material_id = segment.get("material_id")
        if material_id not in materials:
            dangling_materials.append(f"{segment_id}:{material_id}")
        for extra in segment.get("extra_material_refs", []):
            if extra not in materials:
                dangling_extra.append(f"{segment_id}:{extra}")
        timerange = segment.get("target_timerange")
        if isinstance(timerange, dict):
            start = timerange.get("start")
            duration = timerange.get("duration")
            if not isinstance(start, int) or not isinstance(duration, int) or start < 0 or duration < 0:
                invalid_ranges.append(str(segment_id))
            else:
                max_end = max(max_end, start + duration)
    duration = info.get("duration")
    errors: list[str] = []
    if duplicate_segments:
        errors.append(f"duplicate segment IDs: {', '.join(sorted(duplicate_segments))}")
    if dangling_materials:
        errors.append(f"dangling segment material refs: {', '.join(dangling_materials[:10])}")
    if dangling_extra:
        errors.append(f"dangling extra material refs: {', '.join(dangling_extra[:10])}")
    if invalid_ranges:
        errors.append(f"invalid target timeranges: {', '.join(invalid_ranges[:10])}")
    if not isinstance(duration, int) or duration < max_end:
        errors.append(f"draft duration {duration!r} does not cover maximum segment end {max_end}")
    return {
        "valid": not errors,
        "errors": errors,
        "material_ids": len(materials),
        "segment_ids": len(segment_ids),
        "max_segment_end_us": max_end,
    }


def inspect_draft(bundle: DraftBundle) -> dict[str, Any]:
    info = bundle.info
    materials = info.get("materials", {})
    tracks = []
    for track in info.get("tracks", []):
        segments = track.get("segments", [])
        tracks.append(
            {
                "id": track.get("id"),
                "name": track.get("name", ""),
                "type": track.get("type"),
                "flag": track.get("flag"),
                "segment_count": len(segments),
                "track_render_indices": sorted(
                    {segment.get("track_render_index") for segment in segments if isinstance(segment, dict)}
                ),
            }
        )
    video_status = []
    for video in materials.get("videos", []):
        path_value = video.get("path", "")
        path = Path(path_value) if path_value else None
        video_status.append(
            {
                "id": video.get("id"),
                "type": video.get("type"),
                "name": video.get("material_name"),
                "path": path_value,
                "exists": bool(path and path.is_file()),
                "readable": bool(path and path.is_file() and path.stat().st_mode & 0o400),
            }
        )
    references = validate_references(info)
    return {
        "draft_path": str(bundle.path),
        "version": info.get("version"),
        "fps": info.get("fps"),
        "canvas": info.get("canvas_config"),
        "duration_us": info.get("duration"),
        "track_count": len(tracks),
        "segment_count": sum(track["segment_count"] for track in tracks),
        "tracks": tracks,
        "material_counts": {kind: len(items) for kind, items in materials.items() if isinstance(items, list)},
        "media": video_status,
        "references": references,
        "file_hashes": bundle.hashes,
        "template_2_matches_draft_info": (
            bundle.hashes.get("template-2.tmp") == bundle.hashes.get("draft_info.json")
            if bundle.hashes.get("template-2.tmp") is not None
            else None
        ),
        "managed_state": {
            "exists": bundle.state is not None,
            "config_set_id": bundle.state.get("config_set_id") if bundle.state else None,
            "run_id": bundle.state.get("run_id") if bundle.state else None,
        },
    }


def find_track(info: dict[str, Any], *, track_type: str, name: str) -> dict[str, Any]:
    matches = [
        track for track in info.get("tracks", []) if track.get("type") == track_type and track.get("name") == name
    ]
    if len(matches) != 1:
        raise DraftError(f"expected exactly one {track_type!r} track named {name!r}, found {len(matches)}")
    return matches[0]

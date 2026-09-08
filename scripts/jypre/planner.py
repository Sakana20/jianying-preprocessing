from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import LoadedConfig, load_config
from .draft import DraftBundle, find_track, load_draft, material_index, validate_references
from .errors import DraftError, PlanError
from .photos import add_photo_feature, remove_managed_features, reorder_tracks
from .text import apply_subtitle_style
from .util import canonical_json_bytes, frame_ceil, frame_floor, frame_to_us, read_json, sha256_bytes, sha256_file

JOB_FIELDS = {
    "job_schema",
    "draft_path",
    "config_root",
    "config_set",
    "media_manifest",
    "search_roots",
    "media_strategy",
    "permission_strategy",
    "subtitle_track",
    "strict",
}
STRICT_FIELDS = {
    "unmatched_product",
    "unmatched_benefit",
    "unmatched_benefit_image",
    "font_missing",
    "unmanaged_layer_conflict",
}


@dataclass
class PlanBuild:
    plan: dict[str, Any]
    desired: DraftBundle
    config: LoadedConfig
    job: dict[str, Any]


def load_job(path: Path) -> tuple[dict[str, Any], str]:
    try:
        job = read_json(path.expanduser().resolve())
    except (OSError, ValueError) as exc:
        raise PlanError(f"cannot read job: {exc}") from exc
    if not isinstance(job, dict):
        raise PlanError("job must be a JSON object")
    missing = JOB_FIELDS - job.keys()
    extra = job.keys() - JOB_FIELDS
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unknown/inline fields: {', '.join(sorted(extra))}")
        raise PlanError("invalid job; " + "; ".join(details))
    if job.get("job_schema") != 1:
        raise PlanError("job_schema must be 1")
    for key in ("draft_path", "config_root"):
        if not isinstance(job.get(key), str) or not Path(job[key]).is_absolute():
            raise PlanError(f"{key} must be an absolute path")
    if job.get("media_strategy") != "reference-existing":
        raise PlanError("v0.1 only supports media_strategy='reference-existing'")
    if job.get("permission_strategy") != "diagnose-only":
        raise PlanError("v0.1 only supports permission_strategy='diagnose-only'")
    if not isinstance(job.get("search_roots"), list) or any(
        not isinstance(value, str) or not Path(value).is_absolute() for value in job["search_roots"]
    ):
        raise PlanError("search_roots must be an array of absolute paths")
    subtitle = job.get("subtitle_track")
    if not isinstance(subtitle, dict) or set(subtitle) != {"name", "on_ambiguous"}:
        raise PlanError("subtitle_track must contain only name and on_ambiguous")
    if subtitle.get("on_ambiguous") != "fail":
        raise PlanError("v1 only supports subtitle_track.on_ambiguous='fail'")
    strict = job.get("strict")
    if (
        not isinstance(strict, dict)
        or set(strict) != STRICT_FIELDS
        or any(not isinstance(strict[key], bool) for key in STRICT_FIELDS)
    ):
        raise PlanError("strict must contain the five documented boolean fields")
    media_manifest = job.get("media_manifest")
    if media_manifest is not None and (not isinstance(media_manifest, str) or not Path(media_manifest).is_absolute()):
        raise PlanError("media_manifest must be an absolute path or null")
    if media_manifest is not None:
        raise PlanError("v0.1 does not yet consume media_manifest; use null with reference-existing")
    if job["search_roots"]:
        raise PlanError("v0.1 does not yet scan search_roots; use an empty array")
    return job, sha256_file(path.expanduser().resolve())


def _original_subtitle_texts(info: dict[str, Any], track: dict[str, Any]) -> dict[str, str]:
    texts = {item["id"]: item for item in info["materials"]["texts"]}
    result = {}
    for segment in track["segments"]:
        material = texts.get(segment["material_id"])
        if not material:
            raise DraftError(f"subtitle material missing: {segment['material_id']}")
        try:
            result[material["id"]] = json.loads(material["content"])["text"]
        except (TypeError, ValueError, KeyError) as exc:
            raise DraftError(f"invalid subtitle content for {material['id']}: {exc}") from exc
    return result


def _assert_compatible(info: dict[str, Any], config: LoadedConfig) -> None:
    compatibility = config.data["draft_compatibility"]
    if info.get("version") != compatibility["draft_version"]:
        raise DraftError(f"apply supports Draft version {compatibility['draft_version']}, got {info.get('version')}")
    if info.get("fps") != compatibility["fps"]:
        raise DraftError(f"apply supports {compatibility['fps']} fps, got {info.get('fps')}")
    style = config.components["subtitle_style"]
    canvas = info.get("canvas_config", {})
    if not style or (canvas.get("width"), canvas.get("height")) != (
        style["canvas"]["width"],
        style["canvas"]["height"],
    ):
        raise DraftError("Draft canvas does not match the configured exact canvas")


def _business_segments(info: dict[str, Any], track: dict[str, Any]) -> list[dict[str, Any]]:
    materials = material_index(info)
    result = []
    for segment in track["segments"]:
        resolved = materials.get(segment.get("material_id"))
        if resolved and resolved[0] == "videos" and resolved[1].get("type") == "video":
            result.append(segment)
    if not result:
        raise DraftError("business video track contains no video material segments")
    return sorted(result, key=lambda segment: segment["target_timerange"]["start"])


def _media_report(info: dict[str, Any], business: list[dict[str, Any]]) -> dict[str, Any]:
    materials = material_index(info)
    items = []
    for segment in business:
        material = materials[segment["material_id"]][1]
        path = Path(material.get("path", ""))
        items.append(
            {
                "segment_id": segment["id"],
                "material_id": material["id"],
                "path": str(path),
                "exists": path.is_file(),
                "readable": path.is_file() and bool(path.stat().st_mode & 0o400),
            }
        )
    return {"items": items, "all_resolved": all(item["exists"] and item["readable"] for item in items)}


def _unmanaged_asset_conflicts(
    info: dict[str, Any], state: dict[str, Any] | None, config: LoadedConfig
) -> list[dict[str, Any]]:
    if state:
        return []
    configured: list[tuple[str, str]] = []
    risk = config.components.get("risk_warning")
    if risk:
        configured.append(("risk_warning", risk["asset"]["path"]))
    images = config.components.get("benefit_images")
    if images:
        configured.extend(
            (f"benefit_images:{item['benefit_image_id']}", item["asset"]["path"]) for item in images["items"]
        )
    conflicts = []
    for material in info.get("materials", {}).get("videos", []):
        if material.get("type") != "photo":
            continue
        for feature, path in configured:
            if material.get("path") == path:
                conflicts.append({"feature": feature, "material_id": material.get("id"), "path": path})
    return conflicts


def _assign_subtitles(business: list[dict[str, Any]], matched: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    assigned = {segment["id"]: [] for segment in business}
    for match in matched.values():
        timerange = match["target_timerange"]
        start = timerange["start"]
        end = start + timerange["duration"]
        containers = []
        for video in business:
            video_range = video["target_timerange"]
            vstart = video_range["start"]
            vend = vstart + video_range["duration"]
            if vstart <= start and end <= vend:
                containers.append(video["id"])
        if len(containers) != 1:
            raise DraftError(
                f"matched subtitle {match['subtitle_segment_id']} belongs to {len(containers)} business segments"
            )
        match["business_video_segment_id"] = containers[0]
        assigned[containers[0]].append(match)
    return assigned


def _range(start: int, duration: int) -> tuple[int, int]:
    return start, start + duration


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _end_frame_placements(
    info: dict[str, Any], business: list[dict[str, Any]], duration_us: int
) -> tuple[list[tuple[str, dict[str, int]]], int, list[dict[str, Any]]]:
    fps = int(info["fps"])
    frame_duration = frame_floor(duration_us, fps)
    if frame_duration != 90 or frame_to_us(frame_duration, fps) != duration_us:
        raise DraftError("end-frame duration is not exactly 90 frames")
    occupied: list[tuple[str, tuple[int, int]]] = []
    for track in info["tracks"]:
        for segment in track.get("segments", []):
            timerange = segment.get("target_timerange")
            if not timerange:
                continue
            occupied.append(
                (
                    segment["id"],
                    (
                        frame_ceil(timerange["start"], fps),
                        frame_ceil(timerange["start"] + timerange["duration"], fps),
                    ),
                )
            )
    placements = []
    reports = []
    final_frame = frame_ceil(info["duration"], fps)
    for index, segment in enumerate(business):
        source_range = segment["target_timerange"]
        start_frame = frame_ceil(source_range["start"] + source_range["duration"], fps)
        end_frame = start_frame + frame_duration
        collision_ids = [item_id for item_id, interval in occupied if _overlaps((start_frame, end_frame), interval)]
        if collision_ids:
            raise DraftError(f"end frame after {segment['id']} collides with existing segments: {collision_ids[:8]}")
        start_us = frame_to_us(start_frame, fps)
        end_us = frame_to_us(end_frame, fps)
        placements.append((segment["id"], {"start": start_us, "duration": end_us - start_us}))
        reports.append(
            {
                "source_segment_id": segment["id"],
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_us": start_us,
                "duration_us": end_us - start_us,
                "collision_ids": [],
                "extends_draft": index == len(business) - 1 and end_frame > final_frame,
            }
        )
        final_frame = max(final_frame, end_frame)
    return placements, frame_to_us(final_frame, fps), reports


def _changed_files(base: DraftBundle, desired: DraftBundle) -> list[str]:
    names = set(base.documents) | set(desired.documents)
    result = []
    for name in sorted(names):
        before = base.documents.get(name)
        after = desired.documents.get(name)
        if before != after:
            result.append(name)
    return result


def build_plan(job_path: Path, *, require_approved: bool = True) -> PlanBuild:
    job, job_hash = load_job(job_path)
    config = load_config(Path(job["config_root"]), job["config_set"], require_approved=require_approved)
    base = load_draft(Path(job["draft_path"]))
    _assert_compatible(base.info, config)
    base_refs = validate_references(base.info)
    if not base_refs["valid"]:
        raise DraftError("input Draft has invalid references: " + "; ".join(base_refs["errors"]))
    conflicts = _unmanaged_asset_conflicts(base.info, base.state, config)
    if conflicts and job["strict"]["unmanaged_layer_conflict"]:
        raise DraftError(f"unmanaged configured-asset layers already exist: {conflicts}")

    desired = base.clone()
    remove_managed_features(desired.documents, desired.state)
    info = desired.info
    subtitle_track = find_track(info, track_type="text", name=job["subtitle_track"]["name"])
    business_track = find_track(info, track_type="video", name="视频素材")
    business = _business_segments(info, business_track)
    media = _media_report(info, business)
    if not media["all_resolved"]:
        raise DraftError("one or more business media files are missing or unreadable")

    original_texts = None
    if base.state:
        original_texts = base.state.get("subtitle_original_texts")
        if not isinstance(original_texts, dict):
            raise DraftError("managed state lacks subtitle_original_texts; safe reconciliation is impossible")
    else:
        original_texts = _original_subtitle_texts(info, subtitle_track)
    subtitle_stats, matched = apply_subtitle_style(
        info, subtitle_track, config.components, original_texts=original_texts
    )
    strict = job["strict"]
    if strict["unmatched_product"] and any(count == 0 for count in subtitle_stats["product_hits"].values()):
        raise DraftError(f"unmatched product rules: {subtitle_stats['product_hits']}")
    if strict["unmatched_benefit"] and any(count == 0 for count in subtitle_stats["benefit_hits"].values()):
        raise DraftError(f"unmatched benefit rules: {subtitle_stats['benefit_hits']}")
    assigned = _assign_subtitles(business, matched)

    draft_id = str(info.get("id", base.path.name))
    feature_tracks: dict[str, list[str]] = {"benefit_images": [], "risk_warning": [], "end_frame": []}
    features: dict[str, Any] = {"benefit_images": [], "risk_warning": None, "end_frame": []}
    image_reports = []
    images = config.components.get("benefit_images")
    if images:
        for rule in images["items"]:
            required = set(rule["requires_benefit_ids"])
            placements = []
            for video in business:
                hits = [match for match in assigned[video["id"]] if required <= set(match["benefit_ids"])]
                if len(hits) != 1:
                    message = (
                        f"benefit image {rule['benefit_image_id']} matched {len(hits)} subtitles "
                        f"in business segment {video['id']}"
                    )
                    if strict["unmatched_benefit_image"]:
                        raise DraftError(message)
                    continue
                match = hits[0]
                placements.append((match["subtitle_segment_id"], dict(match["target_timerange"])))
                image_reports.append(
                    {
                        "rule_id": rule["benefit_image_id"],
                        "subtitle_segment_id": match["subtitle_segment_id"],
                        "business_video_segment_id": video["id"],
                        "target_timerange": match["target_timerange"],
                    }
                )
            record = add_photo_feature(
                desired.documents,
                draft_id=draft_id,
                feature="benefit_images",
                rule_id=rule["benefit_image_id"],
                asset=rule["asset"],
                placements=placements,
                placement=rule["placement"],
                animation=rule["animation_in"],
                rank="1",
                render_index=2,
                fps=int(info["fps"]),
            )
            feature_tracks["benefit_images"].append(record["track_id"])
            features["benefit_images"].append(record)

    end_reports: list[dict[str, Any]] = []
    end_frame = config.components.get("end_frame")
    if end_frame:
        placements, final_duration, end_reports = _end_frame_placements(info, business, end_frame["duration_us"])
        info["duration"] = final_duration
        record = add_photo_feature(
            desired.documents,
            draft_id=draft_id,
            feature="end_frame",
            rule_id="end-frame",
            asset=end_frame["asset"],
            placements=placements,
            placement={
                "scale_x": 1.0,
                "scale_y": 1.0,
                "transform_x": 0.0,
                "transform_y": 0.0,
                "alpha": 1.0,
                "rotation": 0.0,
            },
            animation=None,
            rank="1",
            render_index=1,
            fps=int(info["fps"]),
        )
        feature_tracks["end_frame"].append(record["track_id"])
        features["end_frame"].append(record)

    risk = config.components.get("risk_warning")
    if risk:
        timerange = {"start": 0, "duration": info["duration"]}
        record = add_photo_feature(
            desired.documents,
            draft_id=draft_id,
            feature="risk_warning",
            rule_id="risk-warning",
            asset=risk["asset"],
            placements=[("draft", timerange)],
            placement={
                "scale_x": 1.0,
                "scale_y": 1.0,
                "transform_x": 0.0,
                "transform_y": 0.0,
                "alpha": 1.0,
                "rotation": 0.0,
            },
            animation=None,
            rank="0",
            render_index=1,
            fps=int(info["fps"]),
        )
        feature_tracks["risk_warning"].append(record["track_id"])
        features["risk_warning"] = record

    reorder_tracks(info, business_track["id"], feature_tracks)
    target_refs = validate_references(info)
    if not target_refs["valid"]:
        raise DraftError("planned Draft has invalid references: " + "; ".join(target_refs["errors"]))
    state = {
        "state_schema": 1,
        "tool_version": "0.1.0",
        "config_set_id": config.config_set_id,
        "component_hashes": config.hashes,
        "base_draft_sha256": base.hashes["draft_info.json"],
        "subtitle_original_texts": original_texts,
        "features": features,
    }
    if (
        base.state
        and base.state.get("config_set_id") == config.config_set_id
        and base.state.get("component_hashes") == config.hashes
    ):
        state["base_draft_sha256"] = base.state.get("base_draft_sha256")
        if base.state.get("run_id"):
            state["run_id"] = base.state["run_id"]
    desired.documents[".jypre/state.json"] = state
    # Mirror draft_info only when the original pair was an exact copy.
    template_sync = base.hashes.get("template-2.tmp") == base.hashes.get("draft_info.json")
    if template_sync:
        desired.documents["template-2.tmp"] = desired.info
    changed_files = _changed_files(base, desired)
    target_hashes = {name: sha256_bytes(canonical_json_bytes(desired.documents[name])) for name in changed_files}
    plan_core = {
        "plan_schema": 1,
        "job_path": str(job_path.expanduser().resolve()),
        "job_sha256": job_hash,
        "draft_path": str(base.path),
        "base_hashes": base.hashes,
        "config_set_id": config.config_set_id,
        "component_hashes": config.hashes,
        "feature_state": {
            slot: "configured" if config.components[slot] is not None else "disabled"
            for slot in ("benefit_images", "risk_warning", "end_frame")
        },
        "changes": {
            "files": changed_files,
            "target_hashes": target_hashes,
            "template_2_sync": template_sync,
            "json_path_allowlist": [
                "draft_info.json.materials.texts[*]",
                "draft_info.json.materials.videos[*] (managed only)",
                "draft_info.json.materials.{canvases,speeds,material_animations,"
                "sound_channel_mappings,vocal_separations}[*] (managed only)",
                "draft_info.json.tracks[*].segments[*].clip (subtitle or managed only)",
                "draft_info.json.tracks[*] (managed tracks and render indices)",
                "draft_info.json.duration (end-frame only)",
                "draft_meta_info.json.draft_materials[type=0] (managed assets only)",
                "key_value.json (managed segment/asset IDs only)",
                "draft_virtual_store.json.draft_virtual_store[type=1] (managed asset IDs only)",
                ".jypre/state.json",
            ],
        },
        "media": media,
        "subtitles": subtitle_stats,
        "benefit_images": image_reports,
        "end_frames": end_reports,
        "unmanaged_conflicts": conflicts,
        "validation": {"base": base_refs, "target": target_refs},
    }
    plan_id = sha256_bytes(canonical_json_bytes(plan_core))
    plan = {**plan_core, "plan_id": plan_id, "no_op": not changed_files}
    desired.documents[".jypre/state.json"].setdefault("run_id", plan_id[:16])
    # The run ID is part of state, so finalize state hash and plan identity once.
    if ".jypre/state.json" in changed_files:
        plan["changes"]["target_hashes"][".jypre/state.json"] = sha256_bytes(
            canonical_json_bytes(desired.documents[".jypre/state.json"])
        )
    final_core = {key: value for key, value in plan.items() if key not in {"plan_id", "no_op"}}
    plan["plan_id"] = sha256_bytes(canonical_json_bytes(final_core))
    if not base.state:
        desired.documents[".jypre/state.json"]["run_id"] = plan["plan_id"][:16]
        plan["changes"]["target_hashes"][".jypre/state.json"] = sha256_bytes(
            canonical_json_bytes(desired.documents[".jypre/state.json"])
        )
    return PlanBuild(plan, desired, config, job)

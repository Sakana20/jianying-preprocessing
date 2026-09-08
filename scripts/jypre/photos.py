from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import DraftError
from .util import frame_ceil, frame_to_us, sha256_file, unique_id

HELPER_KINDS = (
    "speeds",
    "canvases",
    "material_animations",
    "sound_channel_mappings",
    "vocal_separations",
)


def _animation_path(effect_id: str) -> str:
    roots = [
        Path.home() / "Library/Containers/com.lemon.lvpro/Data/Movies/JianyingPro/User Data/Cache/effect",
        Path.home() / "Movies/JianyingPro/User Data/Cache/effect",
    ]
    candidates: set[Path] = set()
    for root in roots:
        directory = root / effect_id
        if directory.is_dir():
            candidates.update(candidate.resolve() for candidate in directory.iterdir() if candidate.is_dir())
    if len(candidates) != 1:
        raise DraftError(f"animation effect {effect_id} resolved to {len(candidates)} cache directories")
    return str(next(iter(candidates)))


def _photo_material(material_id: str, asset: dict[str, Any]) -> dict[str, Any]:
    path = Path(asset["path"])
    return {
        "aigc_type": "none",
        "audio_fade": None,
        "cartoon_path": "",
        "category_id": "",
        "category_name": "local",
        "check_flag": 63487,
        "crop": {
            "lower_left_x": 0.0,
            "lower_left_y": 1.0,
            "lower_right_x": 1.0,
            "lower_right_y": 1.0,
            "upper_left_x": 0.0,
            "upper_left_y": 0.0,
            "upper_right_x": 1.0,
            "upper_right_y": 0.0,
        },
        "crop_ratio": "free",
        "crop_scale": 1.0,
        "duration": 10_800_000_000,
        "extra_type_option": 0,
        "formula_id": "",
        "freeze": None,
        "has_audio": False,
        "height": asset["height"],
        "id": material_id,
        "intensifies_audio_path": "",
        "intensifies_path": "",
        "is_ai_generate_content": False,
        "is_copyright": False,
        "is_text_edit_overdub": False,
        "is_unified_beauty_mode": False,
        "local_id": "",
        "local_material_id": "",
        "material_id": "",
        "material_name": path.name,
        "material_url": "",
        "matting": {
            "flag": 0,
            "has_use_quick_brush": False,
            "has_use_quick_eraser": False,
            "interactiveTime": [],
            "path": "",
            "strokes": [],
        },
        "media_path": "",
        "object_locked": None,
        "origin_material_id": "",
        "path": str(path),
        "picture_from": "none",
        "picture_set_category_id": "",
        "picture_set_category_name": "",
        "request_id": "",
        "reverse_intensifies_path": "",
        "reverse_path": "",
        "smart_motion": None,
        "source": 0,
        "source_platform": 0,
        "stable": {"matrix_path": "", "stable_level": 0, "time_range": {"duration": 0, "start": 0}},
        "team_id": "",
        "type": "photo",
        "video_algorithm": {
            "algorithms": [],
            "complement_frame_config": None,
            "deflicker": None,
            "gameplay_configs": [],
            "motion_blur_config": None,
            "noise_reduction": None,
            "path": "",
            "quality_enhance": None,
            "time_range": None,
        },
        "width": asset["width"],
    }


def _helpers(seed: str, animation: dict[str, Any] | None) -> tuple[list[str], dict[str, dict[str, Any]]]:
    ids = {kind: unique_id(kind, seed) for kind in HELPER_KINDS}
    animation_items: list[dict[str, Any]] = []
    if animation:
        animation_items.append(
            {
                "anim_adjust_params": None,
                "category_id": "in",
                "category_name": "入场",
                "duration": animation["duration_us"],
                "id": animation["effect_id"],
                "material_type": "video",
                "name": animation["name"],
                "panel": "video",
                "path": _animation_path(animation["effect_id"]),
                "platform": "all",
                "request_id": "",
                "resource_id": animation["resource_id"],
                "start": 0,
                "type": "in",
            }
        )
    objects = {
        "speeds": {"curve_speed": None, "id": ids["speeds"], "mode": 0, "speed": 1.0, "type": "speed"},
        "canvases": {
            "album_image": "",
            "blur": 0.0,
            "color": "",
            "id": ids["canvases"],
            "image": "",
            "image_id": "",
            "image_name": "",
            "source_platform": 0,
            "team_id": "",
            "type": "canvas_color",
        },
        "material_animations": {
            "animations": animation_items,
            "id": ids["material_animations"],
            "multi_language_current": "none",
            "type": "sticker_animation",
        },
        "sound_channel_mappings": {
            "audio_channel_mapping": 0,
            "id": ids["sound_channel_mappings"],
            "is_config_open": False,
            "type": "none",
        },
        "vocal_separations": {
            "choice": 0,
            "id": ids["vocal_separations"],
            "production_path": "",
            "time_range": None,
            "type": "vocal_separation",
        },
    }
    ordered = [ids[kind] for kind in HELPER_KINDS]
    return ordered, objects


def _photo_segment(
    segment_id: str,
    material_id: str,
    extra_refs: list[str],
    timerange: dict[str, int],
    placement: dict[str, Any],
    render_index: int,
    fps: int,
) -> dict[str, Any]:
    start_frame = frame_ceil(timerange["start"], fps)
    end_frame = frame_ceil(timerange["start"] + timerange["duration"], fps)
    source_duration = frame_to_us(end_frame - start_frame, fps)
    return {
        "caption_info": None,
        "cartoon": False,
        "clip": {
            "alpha": placement.get("alpha", 1.0),
            "flip": {"horizontal": False, "vertical": False},
            "rotation": placement.get("rotation", 0.0),
            "scale": {"x": placement.get("scale_x", 1.0), "y": placement.get("scale_y", 1.0)},
            "transform": {"x": placement.get("transform_x", 0.0), "y": placement.get("transform_y", 0.0)},
        },
        "common_keyframes": [],
        "enable_adjust": True,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_match_adjust": False,
        "enable_color_wheels": True,
        "enable_lut": True,
        "enable_smart_color_adjust": False,
        "extra_material_refs": extra_refs,
        "group_id": "",
        "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
        "id": segment_id,
        "intensifies_audio": False,
        "is_placeholder": False,
        "is_tone_modify": False,
        "keyframe_refs": [],
        "last_nonzero_volume": 1.0,
        "material_id": material_id,
        "render_index": render_index,
        "responsive_layout": {
            "enable": False,
            "horizontal_pos_layout": 0,
            "size_layout": 0,
            "target_follow": "",
            "vertical_pos_layout": 0,
        },
        "reverse": False,
        "source_timerange": {"start": 0, "duration": source_duration},
        "speed": 1.0,
        "target_timerange": dict(timerange),
        "template_id": "",
        "template_scene": "default",
        "track_attribute": 0,
        "track_render_index": 0,
        "uniform_scale": {"on": True, "value": 1.0},
        "visible": True,
        "volume": 1.0,
    }


def _track(track_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "attribute": 0,
        "flag": 2,
        "id": track_id,
        "is_default_name": True,
        "name": "",
        "segments": segments,
        "type": "video",
    }


def _meta_record(asset_id: str, asset: dict[str, Any]) -> dict[str, Any]:
    path = Path(asset["path"])
    timestamp = int(path.stat().st_mtime)
    return {
        "create_time": int(path.stat().st_birthtime if hasattr(path.stat(), "st_birthtime") else path.stat().st_ctime),
        "duration": 5_000_000,
        "extra_info": path.name,
        "file_Path": str(path),
        "height": asset["height"],
        "id": asset_id,
        "import_time": timestamp,
        "import_time_ms": timestamp * 1_000_000,
        "item_source": 1,
        "md5": "",
        "metetype": "photo",
        "roughcut_time_range": {"duration": -1, "start": -1},
        "sub_time_range": {"duration": -1, "start": -1},
        "type": 0,
        "width": asset["width"],
    }


def _key_value(segment_id: str, asset_key: str, name: str, rank: str) -> dict[str, Any]:
    return {
        "filter_category": "",
        "filter_detail": "",
        "is_brand": 0,
        "is_from_artist_shop": 0,
        "is_vip": "0",
        "keywordSource": "",
        "materialCategory": "media",
        "materialId": asset_key,
        "materialName": name,
        "materialSubcategory": "local",
        "materialSubcategoryId": "",
        "materialThirdcategory": "导入",
        "materialThirdcategoryId": "",
        "material_copyright": "",
        "material_is_purchased": "",
        "rank": rank,
        "rec_id": "",
        "requestId": "",
        "role": "",
        "searchId": "",
        "searchKeyword": "",
        "segmentId": segment_id,
        "team_id": "",
        "textTemplateVersion": "",
    }


def _asset_key_value(asset_key: str, name: str) -> dict[str, Any]:
    value = _key_value(asset_key, asset_key, name, "0")
    value.pop("segmentId")
    value.update(
        {
            "commerce_template_cate": "",
            "commerce_template_pay_status": "",
            "commerce_template_pay_type": "",
            "enter_from": "",
            "is_limited": False,
            "previewed": 0,
            "previewed_before_added": 0,
            "special_effect_loading_type": "",
            "template_author_id": "",
            "template_drafts_price": 0,
            "template_duration": 0,
            "template_fragment_cnt": 0,
            "template_need_purcahse": True,
            "template_type": "",
            "template_use_cnt": 0,
        }
    )
    return value


def _ensure_sidecars(documents: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    meta = documents.setdefault("draft_meta_info.json", {"draft_materials": []})
    kv = documents.setdefault("key_value.json", {})
    virtual = documents.setdefault(
        "draft_virtual_store.json",
        {
            "draft_materials": [],
            "draft_virtual_store": [{"type": 0, "value": []}, {"type": 1, "value": []}, {"type": 2, "value": []}],
        },
    )
    meta_groups = meta.setdefault("draft_materials", [])
    if not any(group.get("type") == 0 for group in meta_groups):
        meta_groups.append({"type": 0, "value": []})
    virtual_groups = virtual.setdefault("draft_virtual_store", [])
    if not any(group.get("type") == 1 for group in virtual_groups):
        virtual_groups.append({"type": 1, "value": []})
    return meta, kv, virtual


def _register_asset(documents: dict[str, Any], asset: dict[str, Any], asset_id: str) -> None:
    meta, _kv, virtual = _ensure_sidecars(documents)
    meta_values = next(group["value"] for group in meta["draft_materials"] if group.get("type") == 0)
    if not any(item.get("id") == asset_id for item in meta_values):
        meta_values.append(_meta_record(asset_id, asset))
    virtual_values = next(group["value"] for group in virtual["draft_virtual_store"] if group.get("type") == 1)
    if not any(item.get("child_id") == asset_id for item in virtual_values):
        virtual_values.append({"child_id": asset_id, "parent_id": ""})


def add_photo_feature(
    documents: dict[str, Any],
    *,
    draft_id: str,
    feature: str,
    rule_id: str,
    asset: dict[str, Any],
    placements: list[tuple[str, dict[str, int]]],
    placement: dict[str, Any],
    animation: dict[str, Any] | None,
    rank: str,
    render_index: int,
    fps: int,
) -> dict[str, Any]:
    info = documents["draft_info.json"]
    track_id = unique_id("track", draft_id, feature, rule_id)
    asset_id = unique_id("asset", draft_id, feature, rule_id, upper=False)
    asset_key = unique_id("asset-key", draft_id, feature, rule_id, upper=False)
    _register_asset(documents, asset, asset_id)
    _meta, kv, _virtual = _ensure_sidecars(documents)
    segments: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for source_id, timerange in placements:
        seed = ":".join((draft_id, feature, rule_id, source_id))
        material_id = unique_id("photo", seed)
        segment_id = unique_id("segment", seed)
        extra_refs, helpers = _helpers(seed, animation)
        info["materials"]["videos"].append(_photo_material(material_id, asset))
        for kind, helper in helpers.items():
            info["materials"][kind].append(helper)
        segments.append(_photo_segment(segment_id, material_id, extra_refs, timerange, placement, render_index, fps))
        kv[segment_id] = _key_value(segment_id, asset_key, Path(asset["path"]).name, rank)
        items.append(
            {
                "source_segment_id": source_id,
                "photo_material_id": material_id,
                "segment_id": segment_id,
                "helper_ids": extra_refs,
            }
        )
    info["tracks"].append(_track(track_id, segments))
    if rank == "0":
        kv.setdefault(asset_key, _asset_key_value(asset_key, Path(asset["path"]).name))
    return {
        "track_id": track_id,
        "asset_record_id": asset_id,
        "asset_key": asset_key,
        "asset_sha256": asset["sha256"],
        "rule_id": rule_id,
        "items": items,
    }


def remove_managed_features(documents: dict[str, Any], state: dict[str, Any] | None) -> None:
    if not state:
        return
    info = documents["draft_info.json"]
    features = state.get("features", {})
    tracks_by_id = {track.get("id"): track for track in info.get("tracks", [])}
    materials_by_id = {
        item.get("id"): (kind, item)
        for kind, values in info.get("materials", {}).items()
        if isinstance(values, list)
        for item in values
        if isinstance(item, dict)
    }
    material_ids: set[str] = set()
    helper_ids: set[str] = set()
    segment_ids: set[str] = set()
    track_ids: set[str] = set()
    asset_ids: set[str] = set()
    asset_keys: set[str] = set()
    for feature_data in features.values():
        records = feature_data if isinstance(feature_data, list) else [feature_data]
        for record in records:
            if not isinstance(record, dict):
                continue
            track_id = record.get("track_id")
            track = tracks_by_id.get(track_id)
            if not track:
                raise DraftError(f"managed state ownership check failed; missing track: {track_id}")
            expected_segment_ids = {item.get("segment_id") for item in record.get("items", [])}
            actual_segment_ids = {item.get("id") for item in track.get("segments", [])}
            if actual_segment_ids != expected_segment_ids:
                raise DraftError(f"managed track {track_id} was modified; refusing to delete or rebuild it")
            track_ids.add(track_id)
            if record.get("asset_record_id"):
                asset_ids.add(record["asset_record_id"])
            if record.get("asset_key"):
                asset_keys.add(record["asset_key"])
            for item in record.get("items", []):
                resolved = materials_by_id.get(item.get("photo_material_id"))
                if not resolved or resolved[0] != "videos" or resolved[1].get("type") != "photo":
                    raise DraftError(f"managed photo material {item.get('photo_material_id')} is missing or changed")
                segment = next(
                    candidate for candidate in track["segments"] if candidate.get("id") == item.get("segment_id")
                )
                if segment.get("material_id") != item.get("photo_material_id") or set(
                    segment.get("extra_material_refs", [])
                ) != set(item.get("helper_ids", [])):
                    raise DraftError(f"managed segment {item.get('segment_id')} identity no longer matches state")
                asset_path = Path(resolved[1].get("path", ""))
                if not asset_path.is_file() or record.get("asset_sha256") != sha256_file(asset_path):
                    raise DraftError(f"managed asset for {track_id} is missing or its content changed")
                material_ids.add(item["photo_material_id"])
                segment_ids.add(item["segment_id"])
                helper_ids.update(item.get("helper_ids", []))
    info["tracks"] = [track for track in info["tracks"] if track.get("id") not in track_ids]
    for kind, values in info.get("materials", {}).items():
        if not isinstance(values, list):
            continue
        remove_ids = material_ids if kind == "videos" else helper_ids
        info["materials"][kind] = [item for item in values if item.get("id") not in remove_ids]
    kv = documents.get("key_value.json", {})
    for segment_id in segment_ids:
        kv.pop(segment_id, None)
    for asset_key in asset_keys:
        kv.pop(asset_key, None)
    meta = documents.get("draft_meta_info.json", {})
    for group in meta.get("draft_materials", []):
        if group.get("type") == 0:
            group["value"] = [item for item in group.get("value", []) if item.get("id") not in asset_ids]
    virtual = documents.get("draft_virtual_store.json", {})
    for group in virtual.get("draft_virtual_store", []):
        if group.get("type") == 1:
            group["value"] = [item for item in group.get("value", []) if item.get("child_id") not in asset_ids]


def reorder_tracks(info: dict[str, Any], business_track_id: str, feature_tracks: dict[str, list[str]]) -> None:
    by_id = {track["id"]: track for track in info["tracks"]}
    managed = {track_id for values in feature_tracks.values() for track_id in values}
    original = [track for track in info["tracks"] if track["id"] not in managed]
    business_index = next(index for index, track in enumerate(original) if track["id"] == business_track_id)
    ordered = original[: business_index + 1]
    for feature in ("end_frame", "benefit_images"):
        ordered.extend(by_id[track_id] for track_id in feature_tracks.get(feature, []))
    remaining = original[business_index + 1 :]
    risk_ids = set(feature_tracks.get("risk_warning", []))
    ordered.extend(track for track in remaining if track["id"] not in risk_ids)
    ordered.extend(by_id[track_id] for track_id in feature_tracks.get("risk_warning", []))
    info["tracks"] = ordered
    for index, track in enumerate(ordered):
        for segment in track.get("segments", []):
            segment["track_render_index"] = index

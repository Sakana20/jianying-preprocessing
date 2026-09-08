from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .util import canonical_json_bytes, normalized_literal, png_info, read_jsonc, sha256_bytes, sha256_file

COMPONENT_SLOTS = {
    "subtitle_style": "subtitle_style",
    "product_names": "product_names",
    "benefit_points": "benefit_points",
    "benefit_images": "benefit_images",
    "risk_warning": "risk_warning",
    "end_frame": "end_frame",
}
NULLABLE_SLOTS = {"benefit_images", "risk_warning", "end_frame"}
COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class LoadedConfig:
    root: Path
    directory: Path
    data: dict[str, Any]
    components: dict[str, dict[str, Any] | None]
    hashes: dict[str, str | None]
    warnings: tuple[str, ...]
    catalog_entry: dict[str, Any]
    config_path: Path

    @property
    def config_set_id(self) -> str:
        return str(self.data["config_set_id"])


def _closed(obj: Any, required: set[str], context: str, errors: list[str]) -> bool:
    if not isinstance(obj, dict):
        errors.append(f"{context}: expected object")
        return False
    missing = required - obj.keys()
    extra = obj.keys() - required
    if missing:
        errors.append(f"{context}: missing fields: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"{context}: unknown fields: {', '.join(sorted(extra))}")
    return not missing and not extra


def _string(value: Any, context: str, errors: list[str], *, nonempty: bool = True) -> bool:
    if not isinstance(value, str) or (nonempty and (not value or value.strip() != value)):
        errors.append(f"{context}: expected a non-empty, trim-stable string")
        return False
    return True


def _style(value: Any, context: str, errors: list[str]) -> None:
    allowed = {"fill", "stroke", "size", "bold"}
    if not isinstance(value, dict):
        errors.append(f"{context}: expected object")
        return
    extra = value.keys() - allowed
    if extra:
        errors.append(f"{context}: unknown fields: {', '.join(sorted(extra))}")
    if "fill" not in value and "stroke" not in value:
        errors.append(f"{context}: fill or stroke is required")
    for key in ("fill", "stroke"):
        if key in value and (not isinstance(value[key], str) or not COLOR.fullmatch(value[key])):
            errors.append(f"{context}.{key}: expected #RRGGBB")
    if "size" in value and not isinstance(value["size"], (int, float)):
        errors.append(f"{context}.size: expected number")
    if "bold" in value and not isinstance(value["bold"], bool):
        errors.append(f"{context}.bold: expected boolean")


def _asset(value: Any, context: str, errors: list[str], *, alpha_field: bool) -> None:
    fields = {"path", "sha256", "width", "height"} | ({"require_alpha"} if alpha_field else set())
    if not _closed(value, fields, context, errors):
        return
    path_value = value.get("path")
    if not isinstance(path_value, str) or not Path(path_value).is_absolute():
        errors.append(f"{context}.path: expected absolute path")
        return
    if not isinstance(value.get("sha256"), str) or not SHA256.fullmatch(value["sha256"]):
        errors.append(f"{context}.sha256: expected 64 lowercase hex characters")
    if not isinstance(value.get("width"), int) or value["width"] <= 0:
        errors.append(f"{context}.width: expected positive integer")
    if not isinstance(value.get("height"), int) or value["height"] <= 0:
        errors.append(f"{context}.height: expected positive integer")
    if alpha_field and not isinstance(value.get("require_alpha"), bool):
        errors.append(f"{context}.require_alpha: expected boolean")
    path = Path(path_value)
    if not path.is_file():
        errors.append(f"{context}.path: file does not exist: {path}")
        return
    try:
        actual_hash = sha256_file(path)
        if actual_hash != value.get("sha256"):
            errors.append(f"{context}.sha256: expected {value.get('sha256')}, got {actual_hash}")
        width, height, has_alpha = png_info(path)
        if (width, height) != (value.get("width"), value.get("height")):
            errors.append(
                f"{context}: configured dimensions {value.get('width')}x{value.get('height')} "
                f"do not match PNG {width}x{height}"
            )
        if alpha_field and value.get("require_alpha") and not has_alpha:
            errors.append(f"{context}: PNG does not contain an alpha channel")
    except (OSError, ValueError) as exc:
        errors.append(f"{context}: cannot validate asset: {exc}")


def _validate_component(slot: str, value: dict[str, Any], errors: list[str]) -> None:
    common = {"schema_version", "kind"}
    if value.get("schema_version") != 1:
        errors.append(f"{slot}.schema_version: only version 1 is supported")
    if value.get("kind") != COMPONENT_SLOTS[slot]:
        errors.append(f"{slot}.kind: expected {COMPONENT_SLOTS[slot]!r}")
    if slot == "subtitle_style":
        fields = common | {"canvas", "font", "size", "fill", "stroke", "stroke_width", "layout_ui"}
        _closed(value, fields, slot, errors)
        canvas = value.get("canvas")
        if _closed(canvas, {"width", "height", "policy"}, f"{slot}.canvas", errors):
            if canvas != {"width": 720, "height": 1280, "policy": "require_exact"}:
                errors.append(f"{slot}.canvas: v1 requires exact 720x1280 canvas")
        font = value.get("font")
        if _closed(font, {"resource_id", "title", "filename_hint"}, f"{slot}.font", errors):
            for key in ("resource_id", "title", "filename_hint"):
                _string(font[key], f"{slot}.font.{key}", errors)
        for key in ("fill", "stroke"):
            if not isinstance(value.get(key), str) or not COLOR.fullmatch(value[key]):
                errors.append(f"{slot}.{key}: expected #RRGGBB")
        if not isinstance(value.get("size"), (int, float)) or value.get("size", 0) <= 0:
            errors.append(f"{slot}.size: expected positive number")
        if not isinstance(value.get("stroke_width"), (int, float)) or not 0 <= value.get("stroke_width", -1) <= 1:
            errors.append(f"{slot}.stroke_width: expected number in [0,1]")
        layout = value.get("layout_ui")
        if _closed(layout, {"position", "scale_percent", "line_spacing"}, f"{slot}.layout_ui", errors):
            position = layout.get("position")
            if _closed(position, {"x", "y", "unit"}, f"{slot}.layout_ui.position", errors):
                if position.get("unit") != "canvas_pixel":
                    errors.append(f"{slot}.layout_ui.position.unit: expected 'canvas_pixel'")
            if layout.get("line_spacing") != 5:
                errors.append(f"{slot}.layout_ui.line_spacing: v1 only supports UI value 5")
    elif slot in {"product_names", "benefit_points"}:
        fields = common | {"items"} | ({"line_break_rules"} if slot == "benefit_points" else set())
        _closed(value, fields, slot, errors)
        items = value.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{slot}.items: expected non-empty array")
        else:
            id_key = "product_id" if slot == "product_names" else "benefit_id"
            expected = {id_key, "literal", "priority", "style"} | ({"aliases"} if slot == "product_names" else set())
            seen_ids: set[str] = set()
            seen_literals: set[str] = set()
            for index, item in enumerate(items):
                context = f"{slot}.items[{index}]"
                if not _closed(item, expected, context, errors):
                    continue
                item_id = item.get(id_key)
                if not isinstance(item_id, str) or not ID.fullmatch(item_id):
                    errors.append(f"{context}.{id_key}: invalid ID")
                elif item_id in seen_ids:
                    errors.append(f"{context}.{id_key}: duplicate ID {item_id!r}")
                else:
                    seen_ids.add(item_id)
                literal = item.get("literal")
                if _string(literal, f"{context}.literal", errors):
                    norm = normalized_literal(literal)
                    if norm in seen_literals:
                        errors.append(f"{context}.literal: duplicate normalized literal {literal!r}")
                    seen_literals.add(norm)
                if not isinstance(item.get("priority"), int):
                    errors.append(f"{context}.priority: expected integer")
                _style(item.get("style"), f"{context}.style", errors)
                if slot == "product_names":
                    aliases = item.get("aliases")
                    if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
                        errors.append(f"{context}.aliases: expected array of strings")
        if slot == "benefit_points":
            rules = value.get("line_break_rules")
            if not isinstance(rules, list):
                errors.append(f"{slot}.line_break_rules: expected array")
            else:
                for index, rule in enumerate(rules):
                    context = f"{slot}.line_break_rules[{index}]"
                    if _closed(rule, {"literal", "replacement"}, context, errors):
                        _string(rule["literal"], f"{context}.literal", errors)
                        if not isinstance(rule["replacement"], str) or not rule["replacement"]:
                            errors.append(f"{context}.replacement: expected non-empty string")
    elif slot == "benefit_images":
        _closed(value, common | {"items"}, slot, errors)
        items = value.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{slot}.items: expected non-empty array")
        else:
            expected = {
                "benefit_image_id",
                "requires_benefit_ids",
                "match_mode",
                "asset",
                "timing",
                "cardinality",
                "placement",
                "animation_in",
            }
            for index, item in enumerate(items):
                context = f"{slot}.items[{index}]"
                if not _closed(item, expected, context, errors):
                    continue
                if not isinstance(item.get("benefit_image_id"), str) or not ID.fullmatch(item["benefit_image_id"]):
                    errors.append(f"{context}.benefit_image_id: invalid ID")
                refs = item.get("requires_benefit_ids")
                if not isinstance(refs, list) or not refs or any(not isinstance(x, str) for x in refs):
                    errors.append(f"{context}.requires_benefit_ids: expected non-empty string array")
                if item.get("match_mode") != "all_in_same_subtitle":
                    errors.append(f"{context}.match_mode: unsupported value")
                if item.get("timing") != "matched_subtitle_timerange":
                    errors.append(f"{context}.timing: unsupported value")
                if item.get("cardinality") != "one_per_business_video_segment":
                    errors.append(f"{context}.cardinality: unsupported value")
                _asset(item.get("asset"), f"{context}.asset", errors, alpha_field=True)
                placement = item.get("placement")
                pfields = {"layer", "scale_x", "scale_y", "transform_x", "transform_y", "alpha", "rotation"}
                if _closed(placement, pfields, f"{context}.placement", errors):
                    if placement.get("layer") != "below_subtitles_above_business_video":
                        errors.append(f"{context}.placement.layer: unsupported value")
                animation = item.get("animation_in")
                if (
                    _closed(
                        animation,
                        {"name", "effect_id", "resource_id", "duration_us"},
                        f"{context}.animation_in",
                        errors,
                    )
                    and animation.get("duration_us") != 900000
                ):
                    errors.append(f"{context}.animation_in.duration_us: v1 requires 900000")
    elif slot == "risk_warning":
        _closed(value, common | {"asset", "placement"}, slot, errors)
        _asset(value.get("asset"), f"{slot}.asset", errors, alpha_field=True)
        placement = value.get("placement")
        if _closed(placement, {"start_us", "duration", "layer"}, f"{slot}.placement", errors):
            if placement != {"start_us": 0, "duration": "draft", "layer": "above_subtitles"}:
                errors.append(f"{slot}.placement: unsupported v1 placement")
    elif slot == "end_frame":
        fields = common | {
            "asset",
            "duration_us",
            "placement",
            "segment_selector",
            "collision_policy",
            "last_segment_policy",
            "risk_overlay_coverage",
        }
        _closed(value, fields, slot, errors)
        _asset(value.get("asset"), f"{slot}.asset", errors, alpha_field=False)
        if value.get("duration_us") != 3_000_000:
            errors.append(f"{slot}.duration_us: v1 requires 3000000")
        expected_values = {
            "placement": "after_each_video_segment",
            "collision_policy": "require_gap",
            "last_segment_policy": "extend_draft",
            "risk_overlay_coverage": "final_draft",
        }
        for key, expected in expected_values.items():
            if value.get(key) != expected:
                errors.append(f"{slot}.{key}: expected {expected!r}")
        selector = value.get("segment_selector")
        if _closed(selector, {"track_type", "track_name", "material_type"}, f"{slot}.segment_selector", errors):
            if selector.get("track_type") != "video" or selector.get("material_type") != "video":
                errors.append(f"{slot}.segment_selector: v1 requires video track and video material")
            _string(selector.get("track_name"), f"{slot}.segment_selector.track_name", errors)


def _load_catalog(root: Path) -> tuple[dict[str, Any], Path]:
    errors: list[str] = []
    catalog_path = root / "catalog.jsonc"
    try:
        catalog = read_jsonc(catalog_path)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read configuration catalog {catalog_path}: {exc}") from exc
    fields = {"schema_version", "kind", "default_config_set", "config_sets"}
    _closed(catalog, fields, "catalog", errors)
    if not isinstance(catalog, dict):
        raise ConfigError("catalog: expected object")
    if catalog.get("schema_version") != 1:
        errors.append("catalog.schema_version: only version 1 is supported")
    if catalog.get("kind") != "preprocess_config_catalog":
        errors.append("catalog.kind: expected 'preprocess_config_catalog'")
    entries = catalog.get("config_sets")
    seen: set[str] = set()
    if not isinstance(entries, list) or not entries:
        errors.append("catalog.config_sets: expected a non-empty array")
    else:
        entry_fields = {"config_set_id", "display_name", "description", "tags", "path", "enabled"}
        for index, entry in enumerate(entries):
            context = f"catalog.config_sets[{index}]"
            if not _closed(entry, entry_fields, context, errors):
                continue
            config_id = entry.get("config_set_id")
            if not isinstance(config_id, str) or not ID.fullmatch(config_id):
                errors.append(f"{context}.config_set_id: invalid ID")
            elif config_id in seen:
                errors.append(f"{context}.config_set_id: duplicate ID {config_id!r}")
            else:
                seen.add(config_id)
            _string(entry.get("display_name"), f"{context}.display_name", errors)
            if not isinstance(entry.get("description"), str):
                errors.append(f"{context}.description: expected string")
            tags = entry.get("tags")
            if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag for tag in tags):
                errors.append(f"{context}.tags: expected an array of non-empty strings")
            reference = entry.get("path")
            if not isinstance(reference, str) or not reference.endswith(".jsonc") or Path(reference).is_absolute():
                errors.append(f"{context}.path: expected a relative .jsonc path")
            elif ".." in Path(reference).parts:
                errors.append(f"{context}.path: parent traversal is forbidden")
            if not isinstance(entry.get("enabled"), bool):
                errors.append(f"{context}.enabled: expected boolean")
    default = catalog.get("default_config_set")
    if not isinstance(default, str) or default not in seen:
        errors.append("catalog.default_config_set: must reference a registered config set")
    if errors:
        raise ConfigError("; ".join(errors))
    return catalog, catalog_path


def list_config_sets(config_root: Path) -> dict[str, Any]:
    root = config_root.expanduser().resolve()
    catalog, catalog_path = _load_catalog(root)
    entries = []
    for entry in catalog["config_sets"]:
        config_path = root / entry["path"]
        entries.append({**entry, "resolved_path": str(config_path), "file_exists": config_path.is_file()})
    return {
        "catalog_path": str(catalog_path),
        "catalog_sha256": sha256_file(catalog_path),
        "default_config_set": catalog["default_config_set"],
        "config_sets": entries,
    }


def load_config(config_root: Path, config_set: str, *, require_approved: bool = False) -> LoadedConfig:
    errors: list[str] = []
    warnings: list[str] = []
    root = config_root.expanduser().resolve()
    if not ID.fullmatch(config_set):
        raise ConfigError("config_set must contain only lowercase letters, digits, and hyphens")
    catalog, catalog_path = _load_catalog(root)
    entries = [entry for entry in catalog["config_sets"] if entry["config_set_id"] == config_set]
    if len(entries) != 1:
        raise ConfigError(f"config_set {config_set!r} is not registered in {catalog_path}")
    entry = entries[0]
    if require_approved and not entry["enabled"]:
        errors.append(f"config_set {config_set!r} is disabled in the catalog")
    unresolved = root / entry["path"]
    try:
        config_path = unresolved.resolve(strict=True)
    except OSError as exc:
        raise ConfigError(f"cannot resolve config file for {config_set!r}: {exc}") from exc
    try:
        config_path.relative_to(root)
    except ValueError as exc:
        raise ConfigError(f"config file for {config_set!r} escapes the configuration root") from exc
    if unresolved.is_symlink():
        errors.append(f"config file for {config_set!r} may not be a symbolic link")
    try:
        config_data = read_jsonc(config_path)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read config set {config_path}: {exc}") from exc
    if not isinstance(config_data, dict):
        raise ConfigError("config: expected object")
    config_fields = {
        "schema_version",
        "kind",
        "config_set_id",
        "display_name",
        "approval",
        "draft_compatibility",
        *COMPONENT_SLOTS.keys(),
    }
    _closed(config_data, config_fields, "config", errors)
    if config_data.get("schema_version") != 1:
        errors.append("config.schema_version: only version 1 is supported")
    if config_data.get("kind") != "preprocess_config_set":
        errors.append("config.kind: expected 'preprocess_config_set'")
    if config_data.get("config_set_id") != config_set:
        errors.append("config.config_set_id: does not match its catalog entry")
    if config_data.get("display_name") != entry["display_name"]:
        errors.append("config.display_name: does not match its catalog entry")
    approval = config_data.get("approval")
    if _closed(approval, {"status", "source"}, "config.approval", errors):
        if approval.get("status") not in {"approved", "draft"}:
            errors.append("config.approval.status: expected 'approved' or 'draft'")
        if require_approved and approval.get("status") != "approved":
            errors.append("config.approval.status: apply requires an approved configuration")
    compatibility = config_data.get("draft_compatibility")
    _closed(compatibility, {"app_version", "draft_version", "fps"}, "config.draft_compatibility", errors)

    components: dict[str, dict[str, Any] | None] = {}
    hashes: dict[str, str | None] = {
        "catalog": sha256_file(catalog_path),
        "config": sha256_file(config_path),
    }
    for slot, expected_kind in COMPONENT_SLOTS.items():
        component = config_data.get(slot)
        if component is None:
            if slot not in NULLABLE_SLOTS:
                errors.append(f"config.{slot}: may not be null")
            components[slot] = None
            hashes[slot] = None
            continue
        if not isinstance(component, dict):
            errors.append(f"{slot}: expected object")
            components[slot] = None
            hashes[slot] = None
            continue
        if component.get("kind") != expected_kind:
            errors.append(f"{slot}.kind: expected {expected_kind!r}")
        _validate_component(slot, component, errors)
        components[slot] = component
        hashes[slot] = sha256_bytes(canonical_json_bytes(component))

    products = components.get("product_names") or {}
    benefits = components.get("benefit_points") or {}
    product_terms: set[str] = set()
    for item in products.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("literal"), str):
            product_terms.add(normalized_literal(item["literal"]))
            for alias in item.get("aliases", []):
                if isinstance(alias, str):
                    product_terms.add(normalized_literal(alias))
    benefit_terms = {
        normalized_literal(item["literal"])
        for item in benefits.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("literal"), str)
    }
    overlap = product_terms & benefit_terms
    if overlap:
        errors.append(f"product/benefit literal conflict: {', '.join(sorted(overlap))}")
    benefit_ids = {item.get("benefit_id") for item in benefits.get("items", []) if isinstance(item, dict)}
    images = components.get("benefit_images") or {}
    for index, item in enumerate(images.get("items", [])):
        if not isinstance(item, dict):
            continue
        for reference in item.get("requires_benefit_ids", []):
            if reference not in benefit_ids:
                errors.append(f"benefit_images.items[{index}].requires_benefit_ids: unknown benefit ID {reference!r}")

    asset_slots: list[tuple[str, dict[str, Any]]] = []
    for slot in ("risk_warning", "end_frame"):
        component = components.get(slot)
        if component and isinstance(component.get("asset"), dict):
            asset_slots.append((slot, component["asset"]))
    if components.get("benefit_images"):
        for index, item in enumerate(components["benefit_images"].get("items", [])):
            if isinstance(item, dict) and isinstance(item.get("asset"), dict):
                asset_slots.append((f"benefit_images[{index}]", item["asset"]))
    for left in range(len(asset_slots)):
        for right in range(left + 1, len(asset_slots)):
            lname, lasset = asset_slots[left]
            rname, rasset = asset_slots[right]
            if lasset.get("path") == rasset.get("path") or lasset.get("sha256") == rasset.get("sha256"):
                errors.append(f"asset identity conflict between {lname} and {rname}")

    if errors:
        raise ConfigError("; ".join(errors))
    return LoadedConfig(
        root=root,
        directory=config_path.parent,
        data=config_data,
        components=components,
        hashes=hashes,
        warnings=tuple(warnings),
        catalog_entry=entry,
        config_path=config_path,
    )


def config_report(config: LoadedConfig) -> dict[str, Any]:
    products = config.components["product_names"]
    benefits = config.components["benefit_points"]
    images = config.components["benefit_images"]
    return {
        "valid": True,
        "config_set_id": config.config_set_id,
        "display_name": config.data["display_name"],
        "config_file": str(config.config_path),
        "enabled": config.catalog_entry["enabled"],
        "approval": config.data["approval"]["status"],
        "component_hashes": config.hashes,
        "resolved_counts": {
            "product_names": len(products["items"]) if products else 0,
            "benefit_points": len(benefits["items"]) if benefits else 0,
            "benefit_image_rules": len(images["items"]) if images else 0,
        },
        "feature_state": {
            slot: "configured" if config.components[slot] is not None else "disabled" for slot in NULLABLE_SLOTS
        },
        "errors": [],
        "warnings": list(config.warnings),
    }

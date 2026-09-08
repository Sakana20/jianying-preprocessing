from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DraftError
from .util import normalized_literal, unique_id


@dataclass(frozen=True)
class TextResult:
    text: str
    content: str
    product_hits: dict[str, int]
    benefit_hits: dict[str, int]
    matched_benefit_ids: frozenset[str]


def _rgb(color: str) -> list[float]:
    return [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]


def _full_style(
    start: int,
    end: int,
    style: dict[str, Any],
    base: dict[str, Any],
    font_path: str,
    font_resource_id: str,
) -> dict[str, Any]:
    fill = style.get("fill", base["fill"])
    stroke = style.get("stroke", base["stroke"])
    return {
        "fill": {"content": {"solid": {"color": _rgb(fill)}}},
        "range": [start, end],
        "strokes": [
            {
                "width": float(base["stroke_width"]),
                "content": {"solid": {"color": _rgb(stroke)}},
            }
        ],
        "useLetterColor": True,
        "size": style.get("size", base["size"]),
        "bold": style.get("bold", False),
        "font": {"path": font_path, "id": font_resource_id},
    }


def compile_text(
    original: str,
    subtitle_style: dict[str, Any],
    products: list[dict[str, Any]],
    benefits: list[dict[str, Any]],
    line_break_rules: list[dict[str, str]],
    font_path: str,
) -> TextResult:
    text = original
    for rule in line_break_rules:
        text = text.replace(rule["literal"], rule["replacement"])
    normalized = normalized_literal(text)
    if len(normalized) != len(text):
        raise DraftError("NFKC changed text length; v1 cannot safely emit rich-text offsets")
    candidates: list[dict[str, Any]] = []
    product_hits: dict[str, int] = {item["product_id"]: 0 for item in products}
    benefit_hits: dict[str, int] = {item["benefit_id"]: 0 for item in benefits}
    for category, items, id_key, _hits in (
        ("product", products, "product_id", product_hits),
        ("benefit", benefits, "benefit_id", benefit_hits),
    ):
        for item in items:
            literals = [item["literal"], *item.get("aliases", [])]
            for literal in literals:
                needle = normalized_literal(literal)
                cursor = 0
                while True:
                    start = normalized.find(needle, cursor)
                    if start < 0:
                        break
                    end = start + len(needle)
                    candidates.append(
                        {
                            "start": start,
                            "end": end,
                            "length": len(needle),
                            "priority": item["priority"],
                            "category": category,
                            "id": item[id_key],
                            "style": item["style"],
                        }
                    )
                    cursor = end
    # Longest match wins; explicit priority breaks equal-length ties.
    candidates.sort(key=lambda item: (-item["length"], -item["priority"], item["start"], item["id"]))
    claimed = [False] * len(text)
    selected = []
    for candidate in candidates:
        if any(claimed[candidate["start"] : candidate["end"]]):
            continue
        selected.append(candidate)
        for index in range(candidate["start"], candidate["end"]):
            claimed[index] = True
        hits = product_hits if candidate["category"] == "product" else benefit_hits
        hits[candidate["id"]] += 1
    selected.sort(key=lambda item: item["start"])
    base = {
        "size": subtitle_style["size"],
        "fill": subtitle_style["fill"],
        "stroke": subtitle_style["stroke"],
        "stroke_width": subtitle_style["stroke_width"],
    }
    ranges: list[dict[str, Any]] = []
    cursor = 0
    for match in selected:
        if cursor < match["start"]:
            ranges.append(
                _full_style(cursor, match["start"], {}, base, font_path, subtitle_style["font"]["resource_id"])
            )
        ranges.append(
            _full_style(
                match["start"], match["end"], match["style"], base, font_path, subtitle_style["font"]["resource_id"]
            )
        )
        cursor = match["end"]
    if cursor < len(text):
        ranges.append(_full_style(cursor, len(text), {}, base, font_path, subtitle_style["font"]["resource_id"]))
    if not text:
        ranges = []
    content = json.dumps({"styles": ranges, "text": text}, ensure_ascii=False, separators=(",", ":"))
    return TextResult(
        text,
        content,
        product_hits,
        benefit_hits,
        frozenset(key for key, count in benefit_hits.items() if count),
    )


def find_font(style: dict[str, Any], info: dict[str, Any]) -> Path:
    resource_id = style["font"]["resource_id"]
    filename = style["font"]["filename_hint"]
    candidates: set[Path] = set()
    for material in info.get("materials", {}).get("texts", []):
        if material.get("font_resource_id") == resource_id:
            candidate = Path(material.get("font_path", ""))
            if candidate.is_file() and candidate.name == filename:
                candidates.add(candidate.resolve())
    cache_roots = [
        Path.home() / "Library/Containers/com.lemon.lvpro/Data/Movies/JianyingPro/User Data/Cache/effect",
        Path.home() / "Movies/JianyingPro/User Data/Cache/effect",
    ]
    if not candidates:
        for root in cache_roots:
            if not root.is_dir():
                continue
            for candidate in root.glob(f"*/*/{filename}"):
                if candidate.is_file():
                    candidates.add(candidate.resolve())
    if len(candidates) != 1:
        raise DraftError(f"font {filename!r} (resource {resource_id}) resolved to {len(candidates)} files")
    return next(iter(candidates))


def apply_subtitle_style(
    info: dict[str, Any],
    track: dict[str, Any],
    config: dict[str, dict[str, Any] | None],
    original_texts: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    subtitle_style = config["subtitle_style"]
    products = config["product_names"]
    benefits = config["benefit_points"]
    if not subtitle_style or not products or not benefits:
        raise DraftError("subtitle configuration components are required")
    font_path = find_font(subtitle_style, info)
    text_materials = {item["id"]: item for item in info["materials"]["texts"]}
    stats: dict[str, Any] = {
        "subtitle_segments": len(track["segments"]),
        "changed_materials": 0,
        "changed_segments": 0,
        "product_hits": {item["product_id"]: 0 for item in products["items"]},
        "benefit_hits": {item["benefit_id"]: 0 for item in benefits["items"]},
        "matched_subtitles": [],
        "font_path": str(font_path),
        "compiled_layout": {
            "scale_x": subtitle_style["layout_ui"]["scale_percent"] / 100,
            "scale_y": subtitle_style["layout_ui"]["scale_percent"] / 100,
            "transform_x": subtitle_style["layout_ui"]["position"]["x"] / 720,
            "transform_y": subtitle_style["layout_ui"]["position"]["y"] / 1280,
            "line_spacing": 0.25,
        },
    }
    matches: dict[str, Any] = {}
    for segment in track["segments"]:
        material = text_materials.get(segment.get("material_id"))
        if material is None:
            raise DraftError(f"subtitle segment {segment.get('id')} has no text material")
        try:
            parsed = json.loads(material["content"])
            original_text = (original_texts or {}).get(material["id"], parsed["text"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DraftError(f"cannot parse subtitle material {material.get('id')}: {exc}") from exc
        result = compile_text(
            original_text,
            subtitle_style,
            products["items"],
            benefits["items"],
            benefits["line_break_rules"],
            str(font_path),
        )
        before_material = json.dumps(material, sort_keys=True, ensure_ascii=False)
        material["content"] = result.content
        material["line_spacing"] = 0.25
        material["check_flag"] = 15
        material["text_color"] = subtitle_style["fill"].lower()
        material["border_color"] = subtitle_style["stroke"].lower()
        material["background_color"] = "#000000"
        material["font_resource_id"] = subtitle_style["font"]["resource_id"]
        material["font_path"] = str(font_path)
        material["fonts"] = [
            {
                "category_id": "",
                "category_name": "",
                "effect_id": subtitle_style["font"]["resource_id"],
                "file_uri": "",
                "id": unique_id("font", material["id"]),
                "path": str(font_path),
                "request_id": "",
                "resource_id": subtitle_style["font"]["resource_id"],
                "source_platform": 0,
                "team_id": "",
                "title": subtitle_style["font"]["title"],
            }
        ]
        if json.dumps(material, sort_keys=True, ensure_ascii=False) != before_material:
            stats["changed_materials"] += 1
        before_segment = json.dumps(segment, sort_keys=True, ensure_ascii=False)
        layout = stats["compiled_layout"]
        segment.setdefault("clip", {}).setdefault("scale", {}).update({"x": layout["scale_x"], "y": layout["scale_y"]})
        segment["clip"].setdefault("transform", {}).update({"x": layout["transform_x"], "y": layout["transform_y"]})
        if json.dumps(segment, sort_keys=True, ensure_ascii=False) != before_segment:
            stats["changed_segments"] += 1
        for key, count in result.product_hits.items():
            stats["product_hits"][key] += count
        for key, count in result.benefit_hits.items():
            stats["benefit_hits"][key] += count
        if result.matched_benefit_ids:
            timerange = dict(segment["target_timerange"])
            match = {
                "subtitle_segment_id": segment["id"],
                "text_material_id": material["id"],
                "text": result.text,
                "benefit_ids": sorted(result.matched_benefit_ids),
                "target_timerange": timerange,
            }
            stats["matched_subtitles"].append(match)
            matches[segment["id"]] = match
    return stats, matches

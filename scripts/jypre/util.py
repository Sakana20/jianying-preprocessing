from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import unicodedata
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def strip_jsonc_comments(text: str) -> str:
    """Remove JSONC comments without changing comment-like text inside strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and following == "/":
            output.extend("  ")
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                output.append(" ")
                index += 1
            continue
        if char == "/" and following == "*":
            output.extend("  ")
            index += 2
            while index < len(text):
                if index + 1 < len(text) and text[index] == "*" and text[index + 1] == "/":
                    output.extend("  ")
                    index += 2
                    break
                output.append(text[index] if text[index] in "\r\n" else " ")
                index += 1
            else:
                raise ValueError("unterminated JSONC block comment")
            continue
        output.append(char)
        index += 1
    return "".join(output)


def read_jsonc(path: Path) -> Any:
    return json.loads(strip_jsonc_comments(path.read_text(encoding="utf-8")))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def normalized_literal(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def frame_floor(us: int, fps: int) -> int:
    return (us * fps) // 1_000_000


def frame_ceil(us: int, fps: int) -> int:
    return (us * fps + 1_000_000 - 1) // 1_000_000


def frame_to_us(frame: int, fps: int) -> int:
    return (frame * 1_000_000) // fps


def png_info(path: Path) -> tuple[int, int, bool]:
    with path.open("rb") as handle:
        header = handle.read(33)
    if len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    width, height, _bits, color_type = struct.unpack(">IIBB", header[16:26])
    # PNG color types 4 and 6 carry an alpha channel. tRNS is deliberately not accepted.
    return width, height, color_type in {4, 6}


def unique_id(namespace: str, *parts: str, upper: bool = True) -> str:
    import uuid

    value = str(uuid.uuid5(uuid.NAMESPACE_URL, "jypre:" + namespace + ":" + ":".join(parts)))
    return value.upper() if upper else value.replace("-", "")


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

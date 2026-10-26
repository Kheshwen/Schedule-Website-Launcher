"""Reading and writing settings.json.

The file is treated as untrusted input: it is size-limited, every value is type-checked, unknown keys
are dropped, and writing is atomic so a crash can't leave a half-written file.
"""
import json
import os
import re

MAX_SETTINGS_BYTES = 64 * 1024
_GEOMETRY_RE = re.compile(r"\d{1,5}x\d{1,5}\+-?\d{1,6}\+-?\d{1,6}")
_TZ_RE = re.compile(r"[A-Za-z0-9_/+-]{1,64}")


def sanitize(data) -> dict:
    """Keeps only values of the right type and range."""
    if not isinstance(data, dict):
        return {}
    clean: dict = {}
    geometry = data.get("geometry")
    if isinstance(geometry, str) and _GEOMETRY_RE.fullmatch(geometry):
        clean["geometry"] = geometry
    for key in ("zoomed", "sort_rev", "dim"):
        if isinstance(data.get(key), bool):
            clean[key] = data[key]
    if data.get("dpi") in (0, 1) and not isinstance(data.get("dpi"), bool):
        clean["dpi"] = data["dpi"]
    if data.get("sort_col") in ("Task", "Next", "Status"):
        clean["sort_col"] = data["sort_col"]
    if data.get("theme") in ("system", "light", "dark"):
        clean["theme"] = data["theme"]
    tz = data.get("tz")
    if isinstance(tz, str) and _TZ_RE.fullmatch(tz):
        clean["tz"] = tz
    return clean


def load_settings(path: str) -> dict:
    try:
        if os.path.getsize(path) > MAX_SETTINGS_BYTES:
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return sanitize(json.load(f))
    except (OSError, ValueError):
        return {}


def save_settings(path: str, data: dict) -> bool:
    """Writes to a temporary file and swaps it in. Returns False if it couldn't be saved."""
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sanitize(data), f)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False

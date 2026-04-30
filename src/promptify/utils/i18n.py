"""Internationalization helpers for loading localized string resources"""

import json
from pathlib import Path
from typing import TypeAlias
from ..core.settings import LOCALE

STRINGS_DIR = Path(__file__).parent.parent.parent.parent / "strings"
RESOURCE_PREFIX = "@res:"
JsonValue: TypeAlias = (
    str | int | float | bool | None | dict[str, "JsonValue"] | list["JsonValue"]
)


def _load_resource_text(locale: str, resource_name: str) -> str | None:
    """Load a locale-scoped text resource, falling back to English when needed"""
    resource_path = STRINGS_DIR / locale / resource_name
    if not resource_path.exists() and locale != "en":
        resource_path = STRINGS_DIR / "en" / resource_name

    if not resource_path.exists():
        return None

    try:
        return resource_path.read_text(encoding="utf-8")
    except Exception:
        return None


def _resolve_json_value(locale: str, value: JsonValue) -> JsonValue:
    """Resolve resource references without changing the public JSON shape"""
    if isinstance(value, str) and value.startswith(RESOURCE_PREFIX):
        resource_name = value.removeprefix(RESOURCE_PREFIX).strip()
        if not resource_name:
            return value
        return _load_resource_text(locale, resource_name) or value

    if isinstance(value, dict):
        return {
            key: _resolve_json_value(locale, nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [_resolve_json_value(locale, nested_value) for nested_value in value]

    return value


def load_strings() -> dict[str, JsonValue]:
    """Load localized strings for the configured locale"""
    file_path = STRINGS_DIR / f"{LOCALE}.json"

    if not file_path.exists():
        file_path = STRINGS_DIR / "en.json"

    if not file_path.exists():
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_strings = json.load(f)
    except Exception:
        return {}

    if not isinstance(raw_strings, dict):
        return {}

    return {
        key: _resolve_json_value(LOCALE, value) for key, value in raw_strings.items()
    }


# GLOBALLY EXPOSED STRING MAP DICTIONARY
strings: dict[str, JsonValue] = load_strings()


def get_string(key: str, default: str = "") -> str:
    """Return a localized string with a plain-string fallback"""
    value = strings.get(key, default)
    return value if isinstance(value, str) else default

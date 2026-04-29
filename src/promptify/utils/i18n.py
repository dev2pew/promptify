"""
INTERNATIONALIZATION (I18N) AND LOCALIZATION UTILITIES.
LOADS LANGUAGE STRINGS FROM JSON TO SUPPORT MULTIPLE REGION DEPLOYMENTS NATIVELY.
"""

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
    """LOADS A LOCALE-SCOPED TEXT RESOURCE, FALLING BACK TO ENGLISH IF NEEDED."""
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
    """RESOLVES RESOURCE REFERENCES WITHOUT CHANGING THE PUBLIC STRING SHAPE."""
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
    """
    LOADS JSON LOCALIZATION STRUCTURES PARSING SYSTEM ENVIRONMENTS CONFIGURATIONS.
    """
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
    """RETURNS A LOCALIZED STRING VALUE WITH A STRICT STRING FALLBACK."""
    value = strings.get(key, default)
    return value if isinstance(value, str) else default

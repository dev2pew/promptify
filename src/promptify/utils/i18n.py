"""
INTERNATIONALIZATION (I18N) AND LOCALIZATION UTILITIES.
LOADS LANGUAGE STRINGS FROM JSON TO SUPPORT MULTIPLE REGION DEPLOYMENTS NATIVELY.
"""

import json
from pathlib import Path
from typing import TypeAlias
from ..core.settings import LOCALE

STRINGS_DIR = Path(__file__).parent.parent.parent.parent / "strings"
JsonValue: TypeAlias = (
    str | int | float | bool | None | dict[str, "JsonValue"] | list["JsonValue"]
)


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
            return json.load(f)
    except Exception:
        return {}


# GLOBALLY EXPOSED STRING MAP DICTIONARY
strings: dict[str, JsonValue] = load_strings()


def get_string(key: str, default: str = "") -> str:
    """RETURNS A LOCALIZED STRING VALUE WITH A STRICT STRING FALLBACK."""
    value = strings.get(key, default)
    return value if isinstance(value, str) else default

"""
Internationalization (i18n) and localization utilities.
Loads language strings from JSON to support multiple region deployments natively and consistently correctly.
"""

import json
from pathlib import Path

from ..core.settings import LOCALE

STRINGS_DIR = Path(__file__).parent.parent.parent.parent / "strings"


def load_strings() -> dict[str, str]:
    """
    Loads JSON localization structures parsing system environments configurations maps natively cleanly gracefully.

    Returns:
        dict[str, str]: Mapped string dictionaries objects variables parsing implementations appropriately consistently correctly natively seamlessly.
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


strings = load_strings()

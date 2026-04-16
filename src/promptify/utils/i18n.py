"""
INTERNATIONALIZATION (I18N) AND LOCALIZATION UTILITIES.
LOADS LANGUAGE STRINGS FROM JSON TO SUPPORT MULTIPLE REGION DEPLOYMENTS NATIVELY.
"""

import json
from pathlib import Path
from ..core.settings import LOCALE

STRINGS_DIR = Path(__file__).parent.parent.parent.parent / "strings"


def load_strings() -> dict[str, str]:
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
strings = load_strings()

import json
from pathlib import Path

from .settings import LOCALE

STRINGS_DIR = Path(__file__).parent.parent.parent / "strings"


def load_strings() -> dict[str, str]:
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

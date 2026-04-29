"""
UNIT TESTS FOR LOCALIZED STRING LOADING AND RESOURCE REFERENCES.
"""

import json
import shutil

from promptify.utils import i18n


def test_load_strings_resolves_locale_resource_references(test_sandbox, monkeypatch):
    """RESOURCE-STYLE STRING ENTRIES SHOULD LOAD THEIR TEXT FROM THE LOCALE FOLDER."""
    strings_dir = test_sandbox["root"] / "i18n_strings"
    if strings_dir.exists():
        shutil.rmtree(strings_dir)
    locale_dir = strings_dir / "en"
    locale_dir.mkdir(parents=True)
    (locale_dir / "help_text.res").write_text("line 1\nline 2\n", encoding="utf-8")
    (strings_dir / "en.json").write_text(
        json.dumps({"help_text": "@res:help_text.res", "plain": "value"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(i18n, "STRINGS_DIR", strings_dir)
    monkeypatch.setattr(i18n, "LOCALE", "en")

    strings = i18n.load_strings()

    assert strings["help_text"] == "line 1\nline 2\n"
    assert strings["plain"] == "value"

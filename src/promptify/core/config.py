"""Handle case configuration and ignore-pattern rules"""

import json
import fnmatch
from pathlib import Path
from typing import Any, cast
import pathspec

from ..ui.logger import log
from .settings import APP_SETTINGS
from ..utils.i18n import get_string


class CaseConfig:
    """Load and validate a workflow case directory configuration"""

    def __init__(self, case_dir: Path):
        self.case_dir = case_dir
        self.config_file = case_dir / "config.json"

        self.name = case_dir.name
        self.types: list[str] = []
        self.ignores_file = ".caseignore"
        self.system_file = "system.md"
        self.prompt_file = "prompt.md"
        self.legacy_file = "legacy.md"

        self.load_config()

    def load_config(self) -> None:
        """Load config values from `config.json` into the instance state"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                    data: dict[str, Any] | None = None
                    if isinstance(raw_data, dict):
                        data = cast(dict[str, Any], raw_data)
                    elif raw_data and isinstance(raw_data, list):
                        first_item = raw_data[0]
                        if isinstance(first_item, dict):
                            data = cast(dict[str, Any], first_item)

                    if not data:
                        return

                    name = data.get("name")
                    if isinstance(name, str) and name:
                        self.name = name

                    types = data.get("types")
                    if isinstance(types, list) and all(
                        isinstance(item, str) for item in types
                    ):
                        self.types = list(types)

                    ignores_file = data.get("ignores")
                    if isinstance(ignores_file, str) and ignores_file:
                        self.ignores_file = ignores_file

                    system_file = data.get("system")
                    if isinstance(system_file, str) and system_file:
                        self.system_file = system_file

                    prompt_file = data.get("prompt")
                    if isinstance(prompt_file, str) and prompt_file:
                        self.prompt_file = prompt_file

                    legacy_file = data.get("legacy")
                    if isinstance(legacy_file, str) and legacy_file:
                        self.legacy_file = legacy_file
            except Exception as err:
                log.warn(
                    get_string("config_parse_failed", "config parse fail - {e}").format(
                        name=self.name, e=err
                    )
                )

    def get_ignore_spec(self, target_project_dir: Path) -> pathspec.PathSpec:
        """Merge default ignores, project `.gitignore`, and case ignores"""
        lines = list(APP_SETTINGS.runtime.default_ignores)

        target_ignore_path = target_project_dir / ".gitignore"
        if target_ignore_path.exists():
            try:
                with open(target_ignore_path, "r", encoding="utf-8") as f:
                    lines.extend(f.readlines())
            except Exception as err:
                log.warn(
                    get_string("gitignore_read_failed", "gitignore fail - {e}").format(
                        e=err
                    )
                )

        case_ignore_path = self.case_dir / self.ignores_file
        if case_ignore_path.exists():
            try:
                with open(case_ignore_path, "r", encoding="utf-8") as f:
                    lines.extend(f.readlines())
            except Exception as err:
                log.warn(
                    get_string(
                        "caseignore_read_failed", "caseignore fail - {e}"
                    ).format(e=err)
                )

        return pathspec.PathSpec.from_lines("gitignore", lines)

    def is_file_allowed(
        self, file_path: Path, target_project_dir: Path, spec: pathspec.PathSpec
    ) -> bool:
        """Return whether a file passes the configured type and ignore rules"""
        rel_path = str(file_path.relative_to(target_project_dir)).replace("\\", "/")

        match_path = rel_path + ("/" if file_path.is_dir() else "")
        if spec.match_file(match_path):
            return False

        if file_path.is_file() and self.types and "*" not in self.types:
            matched = False
            for t in self.types:
                # EXACT MATCH
                if rel_path == t or file_path.name == t:
                    matched = True
                    break

                # GLOB MATCH (.GITHUB/WORKFLOWS/*.YML)
                if fnmatch.fnmatch(rel_path, t) or fnmatch.fnmatch(file_path.name, t):
                    matched = True
                    break

                # EXTENSION MATCH (.TRAVIS.YML, .YML)
                if t.startswith(".") and file_path.name.endswith(t):
                    matched = True
                    break

            if not matched:
                return False

        return True

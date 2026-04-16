"""
HANDLES PROJECT CASE SETTINGS AND GITIGNORE PATH SPECIFICATION RULES.
"""

import json
import fnmatch
from pathlib import Path
import pathspec

from ..ui.logger import log
from ..utils.i18n import strings


class CaseConfig:
    """LOADS AND VALIDATES WORKFLOW CASE DIRECTORY CONFIGURATIONS."""

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
        """ATTEMPTS TO MOUNT JSON PROPERTIES INTO INSTANCE STATE NATIVELY."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]

                    self.name = data.get("name", self.name)
                    self.types = data.get("types", self.types)
                    self.ignores_file = data.get("ignores", self.ignores_file)
                    self.system_file = data.get("system", self.system_file)
                    self.prompt_file = data.get("prompt", self.prompt_file)
                    self.legacy_file = data.get("legacy", self.legacy_file)
            except Exception as e:
                log.warning(
                    strings.get("config_parse_failed", "failed to parse config").format(
                        name=self.name, error=e
                    )
                )

    def get_ignore_spec(self, target_project_dir: Path) -> pathspec.PathSpec:
        """MERGES STANDARD IGNORES, PROJECT GITIGNORE, AND CASEIGNORE INTO ONE PATTERN SPEC."""
        lines = [".git/", ".svn/", "__pycache__/", ".venv/", "node_modules/"]

        target_ignore_path = target_project_dir / ".gitignore"
        if target_ignore_path.exists():
            try:
                with open(target_ignore_path, "r", encoding="utf-8") as f:
                    lines.extend(f.readlines())
            except Exception as e:
                log.warning(
                    strings.get("gitignore_read_failed", "gitignore error").format(
                        error=e
                    )
                )

        case_ignore_path = self.case_dir / self.ignores_file
        if case_ignore_path.exists():
            try:
                with open(case_ignore_path, "r", encoding="utf-8") as f:
                    lines.extend(f.readlines())
            except Exception as e:
                log.warning(
                    strings.get("caseignore_read_failed", "caseignore error").format(
                        error=e
                    )
                )

        return pathspec.PathSpec.from_lines("gitignore", lines)

    def is_file_allowed(
        self, file_path: Path, target_project_dir: Path, spec: pathspec.PathSpec
    ) -> bool:
        """CHECKS IF A GIVEN FILE SATISFIES THE SPECIFIED EXTENSION AND IGNORE RULES."""
        rel_path = str(file_path.relative_to(target_project_dir)).replace("\\", "/")

        match_path = rel_path + ("/" if file_path.is_dir() else "")
        if spec.match_file(match_path):
            return False

        if file_path.is_file() and self.types and "*" not in self.types:
            matched = False
            for t in self.types:
                # 1. EXACT MATCH
                if rel_path == t or file_path.name == t:
                    matched = True
                    break
                # 2. GLOB MATCH (.GITHUB/WORKFLOWS/*.YML)
                if fnmatch.fnmatch(rel_path, t) or fnmatch.fnmatch(file_path.name, t):
                    matched = True
                    break
                # 3. EXTENSION MATCH (.TRAVIS.YML, .YML)
                if t.startswith(".") and file_path.name.endswith(t):
                    matched = True
                    break

            if not matched:
                return False

        return True

import json
import sys
from pathlib import Path

from logger import log

try:
    import pathspec
except ImportError:
    log.error("'pathspec' library is missing. install it using: 'pip install pathspec'")
    sys.exit(1)


class CaseConfig:
    def __init__(self, case_dir: Path):
        self.case_dir = case_dir
        self.config_file = case_dir / "config.json"

        self.name = case_dir.name
        self.types = []
        self.ignores_file = ".caseignore"
        self.system_file = "system.md"
        self.prompt_file = "prompt.md"
        self.legacy_file = "legacy.md"

        self.load_config()

    def load_config(self):
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
                log.warning(f"failed to parse config for {self.name}: {e}")

    def get_ignore_spec(self, target_project_dir: Path) -> pathspec.PathSpec:
        lines = []

        case_ignore_path = self.case_dir / self.ignores_file
        if case_ignore_path.exists():
            with open(case_ignore_path, "r", encoding="utf-8") as f:
                lines.extend(f.readlines())

        target_ignore_path = target_project_dir / ".gitignore"
        if target_ignore_path.exists():
            with open(target_ignore_path, "r", encoding="utf-8") as f:
                lines.extend(f.readlines())

        lines.extend([".git/", ".svn/", "__pycache__/"])

        return pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, lines
        )

    def is_file_allowed(
        self, file_path: Path, target_project_dir: Path, spec: pathspec.PathSpec
    ) -> bool:
        rel_path = str(file_path.relative_to(target_project_dir)).replace("\\", "/")

        match_path = rel_path + ("/" if file_path.is_dir() else "")
        if spec.match_file(match_path):
            return False

        if file_path.is_file() and self.types and "*" not in self.types:
            if file_path.suffix not in self.types:
                return False

        return True

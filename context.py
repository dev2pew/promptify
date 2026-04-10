import os
from pathlib import Path
from config import CaseConfig


class ProjectContext:
    def __init__(self, target_dir: Path, case: CaseConfig):
        self.target_dir = target_dir
        self.case = case
        self.spec = case.get_ignore_spec(target_dir)

    def _get_allowed_files(self, start_dir: Path):
        for root, dirs, files in os.walk(start_dir):
            valid_dirs = []
            for d in dirs:
                dir_path = Path(root) / d
                rel_dir = (
                    str(dir_path.relative_to(self.target_dir)).replace("\\", "/") + "/"
                )
                if not self.spec.match_file(rel_dir):
                    valid_dirs.append(d)
            dirs[:] = valid_dirs

            for file in files:
                file_path = Path(root) / file
                if self.case.is_file_allowed(file_path, self.target_dir, self.spec):
                    yield file_path

    def generate_tree(self) -> str:
        tree_str = ["TREE /F", f"Folder PATH listing for {self.target_dir.name}", "C:."]

        def _build_tree(current_dir: Path, prefix: str = ""):
            try:
                items = sorted(
                    list(current_dir.iterdir()),
                    key=lambda x: (x.is_file(), x.name.lower()),
                )
            except PermissionError:
                return

            valid_items = []
            for item in items:
                if not self.case.is_file_allowed(item, self.target_dir, self.spec):
                    continue
                valid_items.append(item)

            for i, item in enumerate(valid_items):
                is_last = i == len(valid_items) - 1
                connector = "└───" if is_last else "├───"

                tree_str.append(f"{prefix}{connector}{item.name}")

                if item.is_dir():
                    extension = "    " if is_last else "│   "
                    _build_tree(item, prefix + extension)

        _build_tree(self.target_dir)
        return "\n".join(tree_str) + "\n"

    def get_dir_contents(self, rel_dir_path: str) -> str:
        clean_rel_path = rel_dir_path.lstrip("/\\")
        target_path = (self.target_dir / clean_rel_path).resolve()

        if not target_path.exists() or not target_path.is_dir():
            return f"<!-- Error: Directory '{rel_dir_path}' not found -->\n"

        if not str(target_path).startswith(str(self.target_dir.resolve())):
            return f"<!-- Error: Access denied to '{rel_dir_path}' -->\n"

        output = []
        try:
            for file_path in self._get_allowed_files(target_path):
                output.append(
                    self.get_file_content(str(file_path.relative_to(self.target_dir)))
                )
        except Exception as e:
            return f"<!-- Error reading directory: {e} -->\n"

        return "\n".join(output)

    def get_type_contents(self, ext: str) -> str:
        clean_ext = ext.lstrip(".")
        output = []
        try:
            for file_path in self._get_allowed_files(self.target_dir):
                if file_path.suffix.lstrip(".").lower() == clean_ext.lower():
                    output.append(
                        self.get_file_content(
                            str(file_path.relative_to(self.target_dir))
                        )
                    )
        except Exception as e:
            return f"<!-- Error reading files of type '{ext}': {e} -->\n"

        if not output:
            return f"<!-- No files found for type '{ext}' -->\n"
        return "\n".join(output)

    def get_available_extensions(self) -> list:
        if hasattr(self, "_cached_extensions"):
            return self._cached_extensions

        exts = set()
        try:
            for file_path in self._get_allowed_files(self.target_dir):
                ext = file_path.suffix.lstrip(".").lower()
                if ext:
                    exts.add(ext)
        except Exception:
            pass

        self._cached_extensions = sorted(list(exts))
        return self._cached_extensions

    def get_file_content(self, rel_file_path: str) -> str:
        clean_rel_path = rel_file_path.lstrip("/\\")
        target_path = (self.target_dir / clean_rel_path).resolve()

        case_file_path = (self.case.case_dir / clean_rel_path).resolve()

        if case_file_path.exists() and case_file_path.is_file():
            actual_path = case_file_path
            display_path = f"{self.case.case_dir.name}/{clean_rel_path}"
        elif target_path.exists() and target_path.is_file():
            actual_path = target_path
            display_path = clean_rel_path.replace("\\", "/")

            if not str(actual_path).startswith(str(self.target_dir.resolve())):
                return f"<!-- Error: Access denied to '{rel_file_path}' -->\n"
            if not self.case.is_file_allowed(actual_path, self.target_dir, self.spec):
                return f"<!-- Error: File '{rel_file_path}' is ignored -->\n"
        else:
            return f"<!-- Error: File '{rel_file_path}' not found -->\n"

        ext = actual_path.suffix.lstrip(".")
        try:
            with open(actual_path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"- `{display_path}`\n\n```{ext}\n{content}\n```\n"
        except Exception as e:
            return f"<!-- Error reading '{display_path}': {e} -->\n"

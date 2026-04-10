import sys
import os
import shutil
import datetime
import json
from pathlib import Path

from logger import log
from ui import print_columnized, print_modes
from config import CaseConfig
from context import ProjectContext
from resolver import PromptResolver
from editor import InteractiveEditor


def format_short_path(path_str: str) -> str:
    """
    Shortens a path to fit within 50% of the terminal width.
    Falls back to shortening parent directories to 2 chars if needed.
    """
    if not path_str:
        return ""

    term_width = shutil.get_terminal_size((80, 20)).columns
    max_width = max(20, term_width // 2)

    if len(path_str) <= max_width:
        return path_str

    parts = list(Path(path_str).parts)
    if len(parts) <= 2:
        return path_str

    # Phase 1: Try dropping directories from the start (keep at least 5 parts if possible)
    min_kept = min(5, len(parts) - 1)
    for k in range(len(parts) - 1, min_kept - 1, -1):
        candidate = f"...{os.sep}" + os.sep.join(parts[-k:])
        if len(candidate) <= max_width:
            return candidate

    # Phase 2: If still too long, shorten parental directories to 2 chars
    # Keep the last 2 directories fully intact
    for k in range(len(parts) - 1, 1, -1):
        kept_parts = parts[-k:]
        if k > 2:
            mid = [p[:2] for p in kept_parts[:-2]]
            tail = kept_parts[-2:]
            candidate_short = f"...{os.sep}" + os.sep.join(mid + tail)
            if len(candidate_short) <= max_width:
                return candidate_short

    # Fallback: just show the last two parts
    return f"...{os.sep}" + os.sep.join(parts[-2:])


class App:
    def __init__(self):
        self.root_dir = Path(__file__).parent.resolve()
        self.cases_dir = self.root_dir / "cases"
        self.data_dir = self.root_dir / "data"
        self.outs_dir = self.root_dir / "outs"

        self.ensure_directories()

    def ensure_directories(self):
        for d in [self.cases_dir, self.data_dir, self.outs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def get_last_path(self, case_name: str) -> str:
        path_file = self.data_dir / case_name / "last.dat"
        if path_file.exists():
            with open(path_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def save_last_path(self, case_name: str, path: str):
        case_data_dir = self.data_dir / case_name
        case_data_dir.mkdir(parents=True, exist_ok=True)
        with open(case_data_dir / "last.dat", "w", encoding="utf-8") as f:
            f.write(path)

    def get_state(self) -> dict:
        state_file = self.data_dir / "state.json"
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_state(self, state: dict):
        state_file = self.data_dir / "state.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)

    def save_output(self, case_name: str, content: str):
        now = datetime.datetime.now()
        out_dir = self.outs_dir / case_name / f"{now.year}_{now.month}_{now.day}"
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{now.strftime('%H_%M_%S')}.md"
        filepath = out_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        log.success(f'successfully saved output to "{filepath}"')

    def notify_system_prompt(self, case: CaseConfig):
        system_path = case.case_dir / case.system_file
        if system_path.exists():
            log.notice(
                "your selected case contains system prompt. for the best results, be sure to apply it in your preferred AI provider"
            )

    def run(self):
        print(">>> welcome to promptify ---")

        cases = [d for d in self.cases_dir.iterdir() if d.is_dir()]
        if not cases:
            log.error(
                "no cases found in 'cases/' directory. please, create one (e.g., 'cases/python/')"
            )
            return

        print("\n[available cases]")
        case_names = [c.name for c in cases]
        print_columnized(case_names)
        print()

        try:
            case_idx_str = log.input("select case >> ")
            case_idx = int(case_idx_str) - 1
            selected_case_dir = cases[case_idx]
        except (ValueError, IndexError):
            log.error("invalid selection")
            return

        case = CaseConfig(selected_case_dir)

        last_path = self.get_last_path(case.name)
        display_path = format_short_path(last_path)
        path_prompt = (
            f"enter target project path (Default: {display_path}) "
            if display_path
            else "enter target project path "
        )

        target_path_str = log.input(path_prompt).strip()
        if not target_path_str:
            target_path_str = last_path

        target_dir = Path(target_path_str).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            log.error(f"directory '{target_dir}' does not exist")
            return

        self.save_last_path(case.name, str(target_dir))

        context = ProjectContext(target_dir, case)
        resolver = PromptResolver(context)

        print("\n[available modes]")
        modes = [
            ("simple mode", "static fixed prompt based off a template"),
            ("interactive mode", "rich CLI text editor with autocomplete"),
        ]
        print_modes(modes)
        print()

        try:
            mode_str = log.input("select mode >> ")
            mode = int(mode_str)
        except ValueError:
            log.error("invalid selection")
            return

        if mode == 1:
            self.run_legacy_mode(case, resolver)
        elif mode == 2:
            self.run_interactive_mode(case, resolver, context)
        else:
            log.error("invalid mode")

    def run_legacy_mode(self, case: CaseConfig, resolver: PromptResolver):
        legacy_path = case.case_dir / case.legacy_file
        if not legacy_path.exists():
            log.error(f"legacy file '{legacy_path}' not found")
            return

        log.normal("processing legacy template")
        with open(legacy_path, "r", encoding="utf-8") as f:
            content = f.read()

        resolved_content = resolver.resolve(content)
        self.save_output(case.name, resolved_content)
        self.notify_system_prompt(case)

    def run_interactive_mode(
        self, case: CaseConfig, resolver: PromptResolver, context: ProjectContext
    ):
        prompt_path = case.case_dir / case.prompt_file
        initial_text = ""
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                initial_text = f.read()

        state = self.get_state()
        firsttime = state.get("firsttime", True)

        editor = InteractiveEditor(initial_text, context, show_help=firsttime)
        edited_text = editor.run()

        if firsttime:
            state["firsttime"] = False
            self.save_state(state)

        if edited_text is None:
            log.warning("operation cancelled by user")
            return

        log.normal("resolving mentions and generating final prompt")

        resolved_prompt = resolver.resolve(edited_text)
        final_output = resolved_prompt

        self.save_output(case.name, final_output)
        self.notify_system_prompt(case)


if __name__ == "__main__":
    try:
        App().run()
    except KeyboardInterrupt:
        print()
        log.warning("exiting")
        sys.exit(0)

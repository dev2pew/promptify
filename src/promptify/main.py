"""Application entry point and orchestration for `promptify`"""

import sys
import datetime
import asyncio
import aiofiles
import pyperclip
import shutil
import json
from pathlib import Path
from typing import cast

from .ui.logger import log
from .ui.ui import print_columnized, print_modes
from .core.config import CaseConfig
from .core.context import ProjectContext
from .core.indexer import ProjectIndexer
from .core.resolver import PromptResolver
from .core.mods import ModRegistry
from .core.cli import CLIConfig, parse_cli_args
from .core.settings import APP_SETTINGS, consume_settings_warns
from .ui.editor import InteractiveEditor
from .utils.i18n import get_string


class App:
    """Coordinate application state, context, resolver, and UI flows"""

    def __init__(self, cli_config: CLIConfig | None = None):
        self.cli_config = cli_config or CLIConfig()
        self.root_dir = Path(__file__).parent.parent.parent.resolve()
        self.cases_dir = self.root_dir / "cases"
        self.data_dir = self.root_dir / "data"
        self.outs_dir = self.root_dir / "outs"
        self.ensure_directories()
        for warn in consume_settings_warns():
            log.warn(warn)

    def ensure_directories(self) -> None:
        """Ensure the application data directories exist"""
        for d in [self.cases_dir, self.data_dir, self.outs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def get_state(self) -> dict:
        """Load persisted application state from disk"""
        state_file = self.data_dir / "state.json"
        if state_file.exists():
            try:
                async with aiofiles.open(state_file, "r", encoding="utf-8") as f:
                    return json.loads(await f.read())
            except Exception:
                pass
        return {"lastcase_index": None, "paths": {}, "modes": {}}

    async def save_state(self, state: dict) -> None:
        """Persist application state to disk"""
        state_file = self.data_dir / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(state_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(state, indent=4))

    async def get_last_path(self, case_name: str, state: dict) -> str:
        """Return the last target path used for a given case"""
        paths = state.get("paths", {})
        return paths.get(case_name, "")

    async def save_last_path(self, case_name: str, path: str, state: dict) -> None:
        """Persist the last target path used for a given case"""
        if "paths" not in state:
            state["paths"] = {}
        state["paths"][case_name] = path
        await self.save_state(state)

    async def get_last_case_index(self, state: dict, case_count: int) -> int | None:
        """Return the remembered 1-based case index when it still fits the current list"""
        index = state.get("lastcase_index")
        if not isinstance(index, int):
            return None
        if index < 1 or index > case_count:
            return None
        return index

    async def save_last_case_index(self, index: int, state: dict) -> None:
        """Persist the remembered 1-based case index shown in the menu"""
        state["lastcase_index"] = index
        await self.save_state(state)

    def get_case_state_key(self, case: CaseConfig) -> str:
        """Return a stable key for per-case state"""
        try:
            return str(case.case_dir.relative_to(self.cases_dir)).replace("\\", "/")
        except ValueError:
            return case.case_dir.name

    async def get_last_mode(self, case: CaseConfig, state: dict) -> int | None:
        """Return the last selected mode for a given case"""
        modes = state.get("modes", {})
        if not isinstance(modes, dict):
            return None

        mode = modes.get(self.get_case_state_key(case))
        return mode if mode in (1, 2) else None

    async def save_last_mode(self, case: CaseConfig, mode: int, state: dict) -> None:
        """Persist the last selected mode for a given case"""
        if "modes" not in state or not isinstance(state["modes"], dict):
            state["modes"] = {}
        state["modes"][self.get_case_state_key(case)] = mode
        await self.save_state(state)

    async def prompt_with_suggestion(
        self,
        string_key: str,
        fallback: str,
        *,
        suggested_text: str = "",
    ) -> str:
        """Prompt with a shared inline suggestion instead of embedding defaults in labels"""
        prompt_text = get_string(string_key, fallback)
        return (await log.input_async(prompt_text, default=suggested_text)).strip()

    def get_output_case_dir_name(self, case: CaseConfig) -> str:
        """Return the output directory name for a case"""
        return case.case_dir.name

    async def save_output(
        self, case: CaseConfig, content: str, raw_content: str | None = None
    ) -> None:
        """Save rendered output to disk and optionally copy it to the clipboard"""
        now = datetime.datetime.now()
        out_dir = (
            self.outs_dir
            / self.get_output_case_dir_name(case)
            / f"{now.year}_{now.month}_{now.day}"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        time_str = now.strftime("%H_%M_%S")
        filepath = out_dir / f"{time_str}.md"

        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)

        if raw_content and APP_SETTINGS.app_behavior.save_raw_output:
            raw_filepath = out_dir / f"{time_str}.raw"
            async with aiofiles.open(raw_filepath, "w", encoding="utf-8") as f:
                await f.write(raw_content)

        log.success(get_string("saved_output", "saved - {path}").format(path=filepath))

        if APP_SETTINGS.app_behavior.copy_output_to_clipboard:
            try:
                await asyncio.to_thread(pyperclip.copy, content)
                log.success(get_string("copied_clipboard", "copied to clipboard"))
            except Exception as err:
                log.warn(
                    get_string("clipboard_failed", "clip fail - {e}").format(e=err)
                )

    async def run(self) -> None:
        """Run the main application flow"""
        print(get_string("welcome", "welcome to promptify"))

        cases = [d for d in self.cases_dir.iterdir() if d.is_dir()]
        if not cases:
            log.err(get_string("no_cases", "no cases found"))
            log.info(
                get_string("root_dir_shows", "pos - {path}").format(path=self.root_dir)
            )
            return

        state = await self.get_state()

        configs = []
        for d in cases:
            configs.append((CaseConfig(d), d))

        # CASE SELECTION
        selected_case_dir = None
        selected_case_index: int | None = None
        last_path = ""

        if self.cli_config.case:
            matching = [d for c, d in configs if c.name == self.cli_config.case]
            if len(matching) > 1:
                log.err(
                    get_string(
                        "duplicate_case_cli",
                        "multiple cases found for this name, leave only one",
                    ).format(case=self.cli_config.case)
                )
                return
            if not matching:
                log.err(
                    get_string("case_not_found", "not found - {case}").format(
                        case=self.cli_config.case
                    )
                )
                return

            selected_case_dir = matching[0]
            case = CaseConfig(selected_case_dir)
            last_path = await self.get_last_path(case.name, state)
        else:
            name_counts = {}
            for cfg, _ in configs:
                name_counts[cfg.name] = name_counts.get(cfg.name, 0) + 1

            display_items = []
            for cfg, d in configs:
                if name_counts[cfg.name] > 1:
                    display_items.append(f"{cfg.name} <ansigray>({d.name})</ansigray>")
                else:
                    display_items.append(cfg.name)

            lastcase_index = await self.get_last_case_index(state, len(cases))

            print(get_string("available_cases", "available cases"))
            print_columnized(display_items)

            try:
                case_input = await self.prompt_with_suggestion(
                    "select_case",
                    "select case",
                    suggested_text=""
                    if lastcase_index is None
                    else str(lastcase_index),
                )

                if not case_input:
                    log.warn(get_string("operation_cancelled", "operation cancelled"))
                    return
                case_idx = int(case_input) - 1
                if case_idx < 0:
                    raise IndexError
                selected_case_dir = cases[case_idx]
                selected_case_index = case_idx + 1
            except (ValueError, IndexError):
                log.err(get_string("invalid_selection", "invalid selection"))
                return

            case = CaseConfig(selected_case_dir)
            last_path = await self.get_last_path(case.name, state)

        # PATH SELECTION
        if self.cli_config.path:
            target_path_str = self.cli_config.path
        else:
            target_path_str = (
                await self.prompt_with_suggestion(
                    "enter_target_path",
                    "enter target project path",
                    suggested_text=last_path,
                )
                or last_path
            )

        target_dir = Path(target_path_str).resolve()
        if not target_dir.is_dir():
            log.err(
                get_string("dir_not_exist", "not found - {path}").format(
                    path=target_dir
                )
            )
            return

        if selected_case_index is not None:
            await self.save_last_case_index(selected_case_index, state)
        await self.save_last_path(case.name, str(target_dir), state)

        # SETUP PROJECT ENGINE
        has_git = shutil.which("git") is not None
        has_git_folder = (target_dir / ".git").exists()
        if not has_git:
            log.warn(get_string("git_not_found", "git executable not found"))
        if not has_git_folder:
            log.warn(
                get_string("no_git_folder", "not found - .git").format(path=target_dir)
            )

        indexer = ProjectIndexer(target_dir, case)
        await indexer.build_index()
        indexer.start_watching()

        context = ProjectContext(
            target_dir,
            case,
            cast(ProjectIndexer, indexer),
            has_git=has_git and has_git_folder,
        )
        registry = ModRegistry()
        registry.register_defaults()
        resolver = PromptResolver(context, cast(ModRegistry, registry))

        # MODE SELECTION
        mode = None
        if self.cli_config.mode:
            m = self.cli_config.mode.lower()
            if m in ("s", "simple", "l", "legacy", "o", "old"):
                mode = 1
            elif m in ("i", "interactive", "a", "advanced", "e", "editor"):
                mode = 2
            else:
                log.err(get_string("invalid_mode", "invalid mode"))
                indexer.stop_watching()
                return
        elif self.cli_config.case and self.cli_config.path:
            mode = 2  # DEFAULT TO INTERACTIVE MODE IF SKIPPING WIZARD VIA CLI
        else:
            last_mode = await self.get_last_mode(case, state)
            print(get_string("available_modes", "available modes"))
            print_modes(
                [
                    (
                        get_string("mode_simple_name", "simple mode"),
                        get_string("mode_simple_desc", "legacy desc"),
                    ),
                    (
                        get_string("mode_interactive_name", "interactive"),
                        get_string("mode_interactive_desc", "editor desc"),
                    ),
                ]
            )
            try:
                mode_input = await self.prompt_with_suggestion(
                    "select_mode",
                    "select mode",
                    suggested_text="" if last_mode is None else str(last_mode),
                )
                if not mode_input:
                    if last_mode is None:
                        log.warn(
                            get_string("operation_cancelled", "operation cancelled")
                        )
                        indexer.stop_watching()
                        return
                    mode = last_mode
                else:
                    mode = int(mode_input)
            except ValueError:
                log.err(get_string("invalid_selection", "invalid selection"))
                indexer.stop_watching()
                return

        if mode in (1, 2):
            await self.save_last_mode(case, mode, state)

        # EXECUTION
        try:
            if mode == 1:
                await self.run_legacy_mode(case, resolver)
            elif mode == 2:
                await self.run_interactive_mode(case, resolver, indexer)
            else:
                log.err(get_string("invalid_mode", "invalid mode"))
        finally:
            indexer.stop_watching()

    async def run_legacy_mode(self, case: CaseConfig, resolver: PromptResolver) -> None:
        """Run the legacy resolver mode"""
        legacy_path = case.case_dir / case.legacy_file
        if not legacy_path.exists():
            log.err(
                get_string("legacy_not_found", "not found - legacy").format(
                    path=legacy_path
                )
            )
            return

        log.normal(get_string("processing_legacy", "processing legacy"))
        async with aiofiles.open(legacy_path, "r", encoding="utf-8") as f:
            content = await f.read()

        resolved_content = await resolver.resolve_user(content)
        await self.save_output(case, resolved_content)

    async def run_interactive_mode(
        self, case: CaseConfig, resolver: PromptResolver, indexer: ProjectIndexer
    ) -> None:
        """Launch the interactive prompt-toolkit editor"""
        prompt_path = case.case_dir / case.prompt_file
        initial_text = ""
        if prompt_path.exists():
            async with aiofiles.open(prompt_path, "r", encoding="utf-8") as f:
                initial_text = await f.read()

        editor = InteractiveEditor(
            initial_text,
            indexer,
            resolver,
            show_help=APP_SETTINGS.editor_behavior.show_help_on_start,
        )
        edited_text = await editor.run_async()

        if edited_text is None:
            log.warn(get_string("operation_cancelled", "operation cancelled"))
            return

        log.normal(get_string("resolving_mentions", "resolving mentions"))
        final_output = await resolver.resolve_user(edited_text)
        await self.save_output(case, final_output, raw_content=edited_text)


def cli():
    """CLI entry point that starts the asynchronous application loop"""
    config = parse_cli_args()
    try:
        asyncio.run(App(config).run())
    except KeyboardInterrupt:
        print()
        log.warn(get_string("exiting", "exiting"))
        sys.exit(0)

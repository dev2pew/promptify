"""Application entry point and orchestration for `promptify`"""

import asyncio
import datetime
import shutil
import sys
from pathlib import Path
from typing import cast

import aiofiles
import pyperclip

from .ui.logger import log
from .ui.ui import print_columnized, print_modes
from .core.config import CaseConfig
from .core.context import ProjectContext
from .core.indexer import ProjectIndexer
from .core.resolver import PromptResolver
from .core.mods import ModRegistry
from .core.cli import CLIConfig, parse_cli_args
from .core.settings import APP_SETTINGS, consume_settings_warns
from .shared.state import (
    AppState,
    AppStateStore,
    EditorSessionState,
    EditorSessionStateStore,
)
from .ui.dialogs import ask_yes_no_modal
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

    @property
    def state_store(self) -> AppStateStore:
        """Return a state store bound to the current data directory"""
        return AppStateStore(self.data_dir / "state.json")

    @property
    def editor_session_store(self) -> EditorSessionStateStore:
        """Return the persistent restore store for unsaved editor sessions"""
        return EditorSessionStateStore(self.data_dir / "state.dat")

    async def get_state(self) -> AppState:
        """Load persisted application state from disk"""
        return await self.state_store.load()

    async def save_state(self, state: AppState) -> None:
        """Persist application state to disk"""
        await self.state_store.save(state)

    async def prompt_restore_editor_session(self) -> bool:
        """Ask whether a pending interactive-editor session should be restored"""
        return await ask_yes_no_modal(
            title=get_string("restore_session_title", "restore session"),
            text=get_string(
                "restore_session_prompt",
                "an unsaved interactive editor session was found.\n\nrestore it now?",
            ),
        )

    async def get_last_path(self, case_name: str, state: AppState) -> str:
        """Return the last target path used for a given case"""
        return state.get_last_path(case_name)

    async def save_last_path(self, case_name: str, path: str, state: AppState) -> None:
        """Persist the last target path used for a given case"""
        state.save_last_path(case_name, path)
        await self.save_state(state)

    async def get_last_case_index(self, state: AppState, case_count: int) -> int | None:
        """Return the remembered 1-based case index when it still fits the current list"""
        return state.get_last_case_index(case_count)

    async def save_last_case_index(self, index: int, state: AppState) -> None:
        """Persist the remembered 1-based case index shown in the menu"""
        state.save_last_case_index(index)
        await self.save_state(state)

    def get_case_state_key(self, case: CaseConfig) -> str:
        """Return a stable key for per-case state"""
        try:
            return str(case.case_dir.relative_to(self.cases_dir)).replace("\\", "/")
        except ValueError:
            return case.case_dir.name

    async def get_last_mode(self, case: CaseConfig, state: AppState) -> int | None:
        """Return the last selected mode for a given case"""
        return state.get_last_mode(self.get_case_state_key(case))

    async def save_last_mode(
        self, case: CaseConfig, mode: int, state: AppState
    ) -> None:
        """Persist the last selected mode for a given case"""
        state.save_last_mode(self.get_case_state_key(case), mode)
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

    async def build_runtime(
        self,
        case: CaseConfig,
        target_dir: Path,
    ) -> tuple[ProjectIndexer, PromptResolver]:
        """Create the shared indexer and resolver used by both launch paths"""
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
        return indexer, resolver

    async def maybe_restore_editor_session(self) -> bool:
        """Restore a pending editor session before showing the menu wizard"""
        session = await self.editor_session_store.load()
        if session is None:
            return False
        if not await self.prompt_restore_editor_session():
            await self.editor_session_store.delete()
            return False

        case_dir = Path(session.case_dir)
        target_dir = Path(session.target_path)
        if not case_dir.is_dir() or not target_dir.is_dir():
            await self.editor_session_store.delete()
            log.warn(
                get_string(
                    "restore_session_invalid",
                    "saved editor session is no longer valid and was discarded",
                )
            )
            return False

        case = CaseConfig(case_dir)
        indexer, resolver = await self.build_runtime(case, target_dir)
        try:
            await self.run_interactive_mode(
                case,
                resolver,
                indexer,
                initial_text=session.prompt_text,
            )
        finally:
            indexer.stop_watching()
        return True

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
        if (
            self.cli_config.case is None
            and self.cli_config.path is None
            and self.cli_config.mode is None
            and await self.maybe_restore_editor_session()
        ):
            return

        print(get_string("welcome", "promptify"))

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

        indexer, resolver = await self.build_runtime(case, target_dir)

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
        self,
        case: CaseConfig,
        resolver: PromptResolver,
        indexer: ProjectIndexer,
        *,
        initial_text: str | None = None,
    ) -> None:
        """Launch the interactive prompt-toolkit editor"""
        prompt_path = case.case_dir / case.prompt_file
        if initial_text is None:
            initial_text = ""
        if not initial_text and prompt_path.exists():
            async with aiofiles.open(prompt_path, "r", encoding="utf-8") as f:
                initial_text = await f.read()

        session_state = EditorSessionState(
            case_dir=str(case.case_dir.resolve()),
            target_path=str(indexer.target_dir.resolve()),
            prompt_text=initial_text,
        )
        editor = InteractiveEditor(
            initial_text,
            indexer,
            resolver,
            show_help=APP_SETTINGS.editor_behavior.show_help_on_start,
            session_store=self.editor_session_store,
            session_state=session_state,
        )
        edited_text = await editor.run_async()

        if edited_text is None:
            log.warn(get_string("operation_cancelled", "operation cancelled"))
            return

        log.normal(get_string("resolving_mentions", "resolving mentions"))
        final_output = await resolver.resolve_user(edited_text)
        await self.save_output(case, final_output, raw_content=edited_text)
        await self.editor_session_store.delete()


def cli():
    """CLI entry point that starts the asynchronous application loop"""
    config = parse_cli_args()
    try:
        asyncio.run(App(config).run())
    except KeyboardInterrupt:
        print()
        log.warn(get_string("exiting", "exiting"))
        sys.exit(0)

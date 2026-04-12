import sys
import datetime
import asyncio
import aiofiles
import pyperclip
import shutil
import json
from pathlib import Path

from .ui.logger import log
from .ui.ui import print_columnized, print_modes
from .core.config import CaseConfig
from .core.context import ProjectContext
from .core.indexer import ProjectIndexer
from .core.resolver import PromptResolver
from .core.mods import ModRegistry
from .ui.editor import InteractiveEditor
from .utils.i18n import strings


class App:
    def __init__(self):
        self.root_dir = Path(__file__).parent.parent.parent.resolve()
        self.cases_dir = self.root_dir / "cases"
        self.data_dir = self.root_dir / "data"
        self.outs_dir = self.root_dir / "outs"
        self.ensure_directories()

    def ensure_directories(self) -> None:
        for d in [self.cases_dir, self.data_dir, self.outs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def get_state(self) -> dict:
        state_file = self.data_dir / "state.json"
        if state_file.exists():
            try:
                async with aiofiles.open(state_file, "r", encoding="utf-8") as f:
                    return json.loads(await f.read())
            except Exception:
                pass
        return {"lastcase": "", "paths": {}}

    async def save_state(self, state: dict) -> None:
        state_file = self.data_dir / "state.json"
        async with aiofiles.open(state_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(state, indent=4))

    async def get_last_path(self, case_name: str, state: dict) -> str:
        paths = state.get("paths", {})
        return paths.get(case_name, "")

    async def save_last_path(self, case_name: str, path: str, state: dict) -> None:
        if "paths" not in state:
            state["paths"] = {}
        state["paths"][case_name] = path
        state["lastcase"] = case_name
        await self.save_state(state)

    async def save_output(
        self, case_name: str, content: str, raw_content: str | None = None
    ) -> None:
        now = datetime.datetime.now()
        out_dir = self.outs_dir / case_name / f"{now.year}_{now.month}_{now.day}"
        out_dir.mkdir(parents=True, exist_ok=True)
        time_str = now.strftime("%H_%M_%S")
        filepath = out_dir / f"{time_str}.md"

        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)

        if raw_content:
            raw_filepath = out_dir / f"{time_str}.raw"
            async with aiofiles.open(raw_filepath, "w", encoding="utf-8") as f:
                await f.write(raw_content)

        log.success(strings["saved_output"].format(path=filepath))

        try:
            await asyncio.to_thread(pyperclip.copy, content)
            log.success(strings["copied_clipboard"])
        except Exception as e:
            log.warning(strings["clipboard_failed"].format(error=e))

    async def run(self) -> None:
        print(strings["welcome"])

        cases = [d for d in self.cases_dir.iterdir() if d.is_dir()]
        if not cases:
            log.error(strings["no_cases"])
            log.info(strings["root_dir_shows"].format(path=self.root_dir))
            return

        state = await self.get_state()

        configs = []
        for d in cases:
            configs.append((CaseConfig(d), d))

        name_counts = {}
        for cfg, _ in configs:
            name_counts[cfg.name] = name_counts.get(cfg.name, 0) + 1

        display_items = []
        valid_names = []
        for cfg, d in configs:
            valid_names.append(cfg.name)
            if name_counts[cfg.name] > 1:
                display_items.append(f"{cfg.name} <ansigray>({d.name})</ansigray>")
            else:
                display_items.append(cfg.name)

        lastcase = state.get("lastcase", "")
        if lastcase not in valid_names:
            lastcase = ""

        print(strings["available_cases"])
        print_columnized(display_items)

        try:
            prompt_str = strings["select_case"]
            if lastcase:
                prompt_str = f"{prompt_str} ('{lastcase}')"
            case_input = (await log.input_async(prompt_str)).strip()

            if not case_input and lastcase:
                selected_case_dir = next(d for c, d in configs if c.name == lastcase)
            elif not case_input:
                log.warning(strings["operation_cancelled"])
                return
            else:
                case_idx = int(case_input) - 1
                if case_idx < 0:
                    raise IndexError
                selected_case_dir = cases[case_idx]
        except (ValueError, IndexError):
            log.error(strings["invalid_selection"])
            return

        case = CaseConfig(selected_case_dir)
        last_path = await self.get_last_path(case.name, state)

        target_path_str = (
            await log.input_async(strings["enter_target_path"].format(path=last_path))
        ).strip() or last_path

        target_dir = Path(target_path_str).resolve()
        if not target_dir.is_dir():
            log.error(strings["dir_not_exist"].format(path=target_dir))
            return

        await self.save_last_path(case.name, str(target_dir), state)

        has_git = shutil.which("git") is not None
        has_git_folder = (target_dir / ".git").exists()
        if not has_git:
            log.warning(
                strings.get("git_not_found", "git executable not found in system path.")
            )
        if not has_git_folder:
            log.warning(
                strings.get(
                    "no_git_folder", "no .git folder found in '{path}'."
                ).format(path=target_dir)
            )

        indexer = ProjectIndexer(target_dir, case)
        await indexer.build_index()
        indexer.start_watching()

        context = ProjectContext(
            target_dir, case, indexer, has_git=has_git and has_git_folder
        )

        registry = ModRegistry()
        registry.register_defaults()
        resolver = PromptResolver(context, registry)

        print(strings["available_modes"])
        print_modes(
            [
                (strings["mode_simple_name"], strings["mode_simple_desc"]),
                (strings["mode_interactive_name"], strings["mode_interactive_desc"]),
            ]
        )

        try:
            mode_input = (await log.input_async(strings["select_mode"])).strip()
            if not mode_input:
                log.warning(strings["operation_cancelled"])
                return
            mode = int(mode_input)
        except ValueError:
            log.error(strings["invalid_selection"])
            return

        try:
            if mode == 1:
                await self.run_legacy_mode(case, resolver)
            elif mode == 2:
                await self.run_interactive_mode(case, resolver, indexer)
            else:
                log.error(strings["invalid_mode"])
        finally:
            indexer.stop_watching()

    async def run_legacy_mode(self, case: CaseConfig, resolver: PromptResolver) -> None:
        legacy_path = case.case_dir / case.legacy_file
        if not legacy_path.exists():
            log.error(strings["legacy_not_found"].format(path=legacy_path))
            return

        log.normal(strings["processing_legacy"])
        async with aiofiles.open(legacy_path, "r", encoding="utf-8") as f:
            content = await f.read()

        resolved_content = await resolver.resolve_user(content)
        await self.save_output(case.name, resolved_content)

    async def run_interactive_mode(
        self, case: CaseConfig, resolver: PromptResolver, indexer: ProjectIndexer
    ) -> None:
        prompt_path = case.case_dir / case.prompt_file
        initial_text = ""
        if prompt_path.exists():
            async with aiofiles.open(prompt_path, "r", encoding="utf-8") as f:
                initial_text = await f.read()

        editor = InteractiveEditor(initial_text, indexer, resolver)
        edited_text = await editor.run_async()

        if edited_text is None:
            log.warning(strings["operation_cancelled"])
            return

        log.normal(strings["resolving_mentions"])
        final_output = await resolver.resolve_user(edited_text)
        await self.save_output(case.name, final_output, raw_content=edited_text)


def cli():
    try:
        asyncio.run(App().run())
    except KeyboardInterrupt:
        print()
        log.warning(strings.get("exiting", "exiting"))
        sys.exit(0)

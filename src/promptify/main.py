import sys
import datetime
import asyncio
import aiofiles
import pyperclip
from pathlib import Path

from .logger import log
from .ui import print_columnized, print_modes
from .config import CaseConfig
from .context import ProjectContext
from .indexer import ProjectIndexer
from .resolver import PromptResolver
from .editor import InteractiveEditor
from .i18n import strings


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

    async def get_last_path(self, case_name: str) -> str:
        path_file = self.data_dir / case_name / "last.dat"
        if path_file.exists():
            async with aiofiles.open(path_file, "r", encoding="utf-8") as f:
                return (await f.read()).strip()
        return ""

    async def save_last_path(self, case_name: str, path: str) -> None:
        (self.data_dir / case_name).mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(
            self.data_dir / case_name / "last.dat", "w", encoding="utf-8"
        ) as f:
            await f.write(path)

    async def save_output(self, case_name: str, content: str) -> None:
        now = datetime.datetime.now()
        out_dir = self.outs_dir / case_name / f"{now.year}_{now.month}_{now.day}"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{now.strftime('%H_%M_%S')}.md"

        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)

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

        print(strings["available_cases"])
        print_columnized([c.name for c in cases])

        try:
            case_input = (await log.input_async(strings["select_case"])).strip()
            if not case_input:
                log.warning(strings["operation_cancelled"])
                return
            case_idx = int(case_input) - 1
            if case_idx < 0:
                raise IndexError
            selected_case_dir = cases[case_idx]
        except (ValueError, IndexError):
            log.error(strings["invalid_selection"])
            return

        case = CaseConfig(selected_case_dir)
        last_path = await self.get_last_path(case.name)

        target_path_str = (
            await log.input_async(strings["enter_target_path"].format(path=last_path))
        ).strip() or last_path

        target_dir = Path(target_path_str).resolve()
        if not target_dir.is_dir():
            log.error(strings["dir_not_exist"].format(path=target_dir))
            return

        await self.save_last_path(case.name, str(target_dir))

        indexer = ProjectIndexer(target_dir, case)
        await indexer.build_index()
        indexer.start_watching()

        context = ProjectContext(target_dir, case, indexer)
        resolver = PromptResolver(context)

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

        editor = InteractiveEditor(initial_text, indexer)
        edited_text = await editor.run_async()

        if edited_text is None:
            log.warning(strings["operation_cancelled"])
            return

        log.normal(strings["resolving_mentions"])
        final_output = await resolver.resolve_user(edited_text)
        await self.save_output(case.name, final_output)


def cli():
    try:
        asyncio.run(App().run())
    except KeyboardInterrupt:
        print()
        log.warning(strings.get("exiting", "exiting"))
        sys.exit(0)

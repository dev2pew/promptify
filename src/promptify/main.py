import sys
import datetime
import asyncio
from pathlib import Path

from .logger import log
from .ui import print_columnized, print_modes
from .config import CaseConfig
from .context import ProjectContext
from .indexer import ProjectIndexer
from .resolver import PromptResolver
from .editor import InteractiveEditor


class App:
    def __init__(self):
        self.root_dir = Path(__file__).parent.parent.parent.resolve()
        self.cases_dir = self.root_dir / "cases"
        self.data_dir = self.root_dir / "data"
        self.outs_dir = self.root_dir / "outs"
        self.ensure_directories()

    def ensure_directories(self):
        for d in [self.cases_dir, self.data_dir, self.outs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def get_last_path(self, case_name: str) -> str:
        path_file = self.data_dir / case_name / "last.dat"
        return (
            path_file.read_text(encoding="utf-8").strip() if path_file.exists() else ""
        )

    def save_last_path(self, case_name: str, path: str):
        (self.data_dir / case_name).mkdir(parents=True, exist_ok=True)
        (self.data_dir / case_name / "last.dat").write_text(path, encoding="utf-8")

    def save_output(self, case_name: str, content: str):
        now = datetime.datetime.now()
        out_dir = self.outs_dir / case_name / f"{now.year}_{now.month}_{now.day}"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{now.strftime('%H_%M_%S')}.md"
        filepath.write_text(content, encoding="utf-8")
        log.success(f"successfully saved output - '{filepath}'")

    async def run(self):
        print(">>> welcome to promptify ---")

        cases = [d for d in self.cases_dir.iterdir() if d.is_dir()]
        if not cases:
            log.error("no cases found in 'cases/' directory")
            log.info(f"self.root_dir shows '{self.root_dir}'")
            return

        print("\n[available cases]")
        print_columnized([c.name for c in cases])

        try:
            case_input = log.input("select case >> ").strip()
            if not case_input:
                log.warning("operation cancelled")
                return
            case_idx = int(case_input) - 1
            if case_idx < 0:
                raise IndexError
            selected_case_dir = cases[case_idx]
        except (ValueError, IndexError):
            log.error("invalid selection")
            return

        case = CaseConfig(selected_case_dir)
        last_path = self.get_last_path(case.name)
        target_path_str = (
            log.input(f"enter target project path ('{last_path}') >> ").strip()
            or last_path
        )

        target_dir = Path(target_path_str).resolve()
        if not target_dir.is_dir():
            log.error(f"directory '{target_dir}' does not exist")
            return

        self.save_last_path(case.name, str(target_dir))

        # CORE COMPONENTS BOOTSTRAPPING
        indexer = ProjectIndexer(target_dir, case)
        await indexer.build_index()
        indexer.start_watching()

        context = ProjectContext(target_dir, case, indexer)
        resolver = PromptResolver(context)

        print("\n[available modes]")
        print_modes(
            [
                ("simple mode", "static fixed prompt based off a template"),
                ("interactive mode", "rich CLI text editor with autocomplete"),
            ]
        )

        try:
            mode_input = log.input("select mode >> ").strip()
            if not mode_input:
                log.warning("operation cancelled.")
                return
            mode = int(mode_input)
        except ValueError:
            log.error("invalid selection")
            return

        try:
            if mode == 1:
                await self.run_legacy_mode(case, resolver)
            elif mode == 2:
                await self.run_interactive_mode(case, resolver, indexer)
            else:
                log.error("invalid mode")
        finally:
            indexer.stop_watching()

    async def run_legacy_mode(self, case: CaseConfig, resolver: PromptResolver):
        legacy_path = case.case_dir / case.legacy_file
        if not legacy_path.exists():
            log.error(f"legacy file '{legacy_path}' not found")
            return

        log.normal("processing legacy template")
        content = legacy_path.read_text(encoding="utf-8")

        # CHANGED: USING RESOLVE_USER (SINGLE-PASS) FOR SAFETY AGAINST SOURCE CODE MENTIONS
        resolved_content = await resolver.resolve_user(content)
        self.save_output(case.name, resolved_content)

    async def run_interactive_mode(
        self, case: CaseConfig, resolver: PromptResolver, indexer: ProjectIndexer
    ):
        prompt_path = case.case_dir / case.prompt_file
        initial_text = (
            prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        )

        editor = InteractiveEditor(initial_text, indexer)
        edited_text = await editor.run_async()

        if edited_text is None:
            log.warning("operation cancelled by user")
            return

        log.normal("resolving mentions")
        final_output = await resolver.resolve_user(edited_text)
        self.save_output(case.name, final_output)


def cli():
    try:
        asyncio.run(App().run())
    except KeyboardInterrupt:
        print()
        log.warning("exiting")
        sys.exit(0)


if __name__ == "__main__":
    cli()

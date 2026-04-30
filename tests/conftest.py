"""Pytest configuration and sandbox bootstrapping for the `promptify` suite"""

import pytest
import shutil
import sys
from pathlib import Path
from typing import cast

# ADD THE SRC FOLDER TO THE PATH SO TESTS CAN IMPORT OUR MODULES NATIVELY
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promptify.core.config import CaseConfig
from promptify.core.indexer import ProjectIndexer
from promptify.core.context import ProjectContext
from promptify.core.resolver import PromptResolver
from promptify.core.mods import ModRegistry


@pytest.fixture(scope="session")
def test_sandbox():
    """
    Create a fully isolated environment for testing.

    The sandbox is cleaned up automatically after the tests complete.
    """
    root = Path(__file__).parent / "sandbox"
    demo_dir = root / "demo"
    case_dir = root / "cases" / "test"
    outs_dir = root / "outs"

    # CLEAN PREVIOUS INTERRUPTED RUNS IF THEY EXIST
    if root.exists():
        shutil.rmtree(root)

    # CREATE DIRECTORIES
    demo_dir.mkdir(parents=True)
    case_dir.mkdir(parents=True)
    outs_dir.mkdir(parents=True)

    # GENERATE DEMO PROJECT FILES
    # 20-LINE FILE FOR RANGE TESTING
    lines = [f"print('This is line {i}')" for i in range(1, 21)]
    (demo_dir / "app.py").write_text("\n".join(lines), encoding="utf-8")

    # RECURSIVE TRAP FILE (MENTIONS ITSELF AND THE PROJECT)
    (demo_dir / "trap.md").write_text(
        "Look at this loop: <@file:trap.md>\nAnd tree: [@project]", encoding="utf-8"
    )

    # IGNORED FILE
    (demo_dir / "secret.key").write_text("SUPER_SECRET_DATA", encoding="utf-8")

    # .GITIGNORE AND TEST.LOG
    (demo_dir / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (demo_dir / "test.log").write_text("log data", encoding="utf-8")

    # SRC DIR
    src_dir = demo_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (src_dir / "utils.py").write_text("def util():\n    pass\n", encoding="utf-8")

    # GENERATE CASE CONFIGURATION
    (case_dir / "config.json").write_text(
        '{"name": "test_case", "types": ["*"]}', encoding="utf-8"
    )
    (case_dir / ".caseignore").write_text("*.key\n", encoding="utf-8")
    (case_dir / "system.md").write_text(
        "You are a helpful assistant.", encoding="utf-8"
    )
    (case_dir / "legacy.md").write_text("Analyze: <@file:app.py>", encoding="utf-8")

    yield {"root": root, "demo": demo_dir, "case": case_dir, "outs": outs_dir}

    # TEARDOWN SANDBOX
    if root.exists():
        shutil.rmtree(root)


@pytest.fixture
async def app_components(
    test_sandbox,
) -> tuple[ProjectContext, PromptResolver]:
    """Bootstrap core logic components that point to the dynamic sandbox"""
    case = CaseConfig(test_sandbox["case"])
    indexer = ProjectIndexer(test_sandbox["demo"], case)
    await indexer.build_index()

    context = ProjectContext(test_sandbox["demo"], case, cast(ProjectIndexer, indexer))
    registry = ModRegistry()
    registry.register_defaults()

    resolver = PromptResolver(context, cast(ModRegistry, registry))

    return context, resolver

import pytest
import shutil
import asyncio
import sys
from pathlib import Path

# Add the src folder to the path so tests can import our modules natively
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promptify.config import CaseConfig
from promptify.indexer import ProjectIndexer
from promptify.context import ProjectContext
from promptify.resolver import PromptResolver

@pytest.fixture(scope="session")
def test_sandbox():
    """
    Creates a fully dynamic, isolated environment for testing.
    Automatically cleans up after tests are completed.
    """
    root = Path(__file__).parent / "sandbox"
    demo_dir = root / "demo"
    case_dir = root / "cases" / "test"
    outs_dir = root / "outs"

    # Clean previous interrupted runs if they exist
    if root.exists():
        shutil.rmtree(root)

    # 1. Create Directories
    demo_dir.mkdir(parents=True)
    case_dir.mkdir(parents=True)
    outs_dir.mkdir(parents=True)

    # 2. Generate Demo Project Files
    # 20-line file for range testing
    lines = [f"print('This is line {i}')" for i in range(1, 21)]
    (demo_dir / "app.py").write_text("\n".join(lines), encoding="utf-8")

    # Recursive trap file (mentions itself and the project)
    (demo_dir / "trap.md").write_text("Look at this loop: <@file:trap.md>\nAnd tree: [@project]", encoding="utf-8")

    # Ignored file
    (demo_dir / "secret.key").write_text("SUPER_SECRET_DATA", encoding="utf-8")

    # 3. Generate Case Configuration
    (case_dir / "config.json").write_text('{"name": "test_case", "types": ["*"]}', encoding="utf-8")
    (case_dir / ".caseignore").write_text("*.key", encoding="utf-8")
    (case_dir / "system.md").write_text("You are a helpful assistant.", encoding="utf-8")
    (case_dir / "legacy.md").write_text("Analyze: <@file:app.py>", encoding="utf-8")

    yield {"root": root, "demo": demo_dir, "case": case_dir, "outs": outs_dir}

    # 4. Teardown Sandbox
    if root.exists():
        shutil.rmtree(root)

@pytest.fixture
async def app_components(test_sandbox):
    """
    Bootstraps the core logic components pointing to the dynamic sandbox.
    """
    case = CaseConfig(test_sandbox["case"])
    indexer = ProjectIndexer(test_sandbox["demo"], case)
    await indexer.build_index()

    context = ProjectContext(test_sandbox["demo"], case, indexer)
    resolver = PromptResolver(context)

    return context, resolver

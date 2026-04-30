"""Pytest configuration and sandbox bootstrapping for the `promptify` suite"""
# ruff: noqa: E402

import os
import pytest
import shutil
import sys
from pathlib import Path
from typing import cast

# ADD THE SRC FOLDER TO THE PATH SO TESTS CAN IMPORT OUR MODULES NATIVELY
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from _settings_master import (
    SettingsPass,
    build_settings_passes,
    install_settings_master_env,
)

install_settings_master_env(os.environ)

from promptify.core.config import CaseConfig
from promptify.core.indexer import ProjectIndexer
from promptify.core.context import ProjectContext
from promptify.core.resolver import PromptResolver
from promptify.core.mods import ModRegistry
from promptify.core.settings import AppSettings, build_settings
from promptify.core.terminal import TerminalProfile, detect_terminal_profile


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


@pytest.fixture(scope="session")
def settings_passes() -> tuple[SettingsPass, ...]:
    """Return the centralized deterministic settings matrix"""
    return build_settings_passes()


@pytest.fixture(params=build_settings_passes(), ids=lambda item: item.name)
def settings_pass(request) -> SettingsPass:
    """Iterate through the shared multi-pass settings matrix"""
    return cast(SettingsPass, request.param)


@pytest.fixture
def apply_settings_pass(monkeypatch):
    """Patch imported APP_SETTINGS bindings to a generated settings pass"""

    def _apply(
        settings_pass: SettingsPass,
    ) -> tuple[AppSettings, list[str], TerminalProfile]:
        settings, warns = build_settings(settings_pass.env)

        import promptify.core.settings as settings_module
        import promptify.core.terminal as terminal_module

        monkeypatch.setattr(settings_module, "APP_SETTINGS", settings)
        monkeypatch.setattr(settings_module, "SETTINGS_WARNINGS", warns)

        monkeypatch.setattr(terminal_module, "APP_SETTINGS", settings)
        terminal_profile = detect_terminal_profile(
            env=settings_pass.env,
            override=settings.terminal.profile,
        )
        monkeypatch.setattr(terminal_module, "APP_TERMINAL_PROFILE", terminal_profile)

        module_names = (
            "promptify.core.config",
            "promptify.core.indexer",
            "promptify.core.matching",
            "promptify.core.mods",
            "promptify.core.resolver",
            "promptify.main",
            "promptify.ui.editor",
            "promptify.ui.logger",
            "promptify.ui.ui",
        )
        for module_name in module_names:
            module = sys.modules.get(module_name)
            if module is None or not hasattr(module, "APP_SETTINGS"):
                continue
            monkeypatch.setattr(module, "APP_SETTINGS", settings, raising=False)
            if hasattr(module, "APP_TERMINAL_PROFILE"):
                monkeypatch.setattr(
                    module,
                    "APP_TERMINAL_PROFILE",
                    terminal_profile,
                    raising=False,
                )

        return settings, warns, terminal_profile

    return _apply

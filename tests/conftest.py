"""Pytest configuration and sandbox bootstrapping for the `promptify` suite"""
# ruff: noqa: E402

import os
import pytest
import shutil
import sys
from collections.abc import Generator
from pathlib import Path
from typing import cast

# ADD THE SRC FOLDER TO THE PATH SO TESTS CAN IMPORT OUR MODULES NATIVELY
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from ._settings_master import (
    SettingsPass,
    build_settings_passes,
    install_settings_master_env,
)
from ._types import (
    AppComponents,
    ApplySettingsPass,
    FixtureRequest,
    MonkeyPatch,
    SandboxPaths,
)

_ = install_settings_master_env(os.environ)

from promptify.core.config import CaseConfig
from promptify.core.indexer import ProjectIndexer
from promptify.core.context import ProjectContext
from promptify.core.resolver import PromptResolver
from promptify.core.mods import ModRegistry
from promptify.core.settings import AppSettings, build_settings
from promptify.core.terminal import TerminalProfile, detect_terminal_profile


def _iter_test_sandbox_roots(tests_dir: Path | None = None) -> tuple[Path, ...]:
    """Return repo-local sandbox directories reserved for pytest runs"""
    resolved_tests_dir = Path(__file__).parent if tests_dir is None else tests_dir
    return tuple(
        path
        for path in resolved_tests_dir.iterdir()
        if path.is_dir() and path.name.startswith("sandbox")
    )


def _cleanup_test_sandbox_roots(tests_dir: Path | None = None) -> None:
    """Remove any repo-local sandbox directories left behind by test runs"""
    for root in _iter_test_sandbox_roots(tests_dir):
        shutil.rmtree(root)


def pytest_sessionstart(session: pytest.Session) -> None:
    """Clear stale repo-local test sandboxes before the suite starts"""
    del session
    _cleanup_test_sandbox_roots()


def pytest_sessionfinish(
    session: pytest.Session, exitstatus: int | pytest.ExitCode
) -> None:
    """Clear repo-local test sandboxes after the suite finishes"""
    del session, exitstatus
    _cleanup_test_sandbox_roots()


@pytest.fixture(scope="session")
def test_sandbox() -> Generator[SandboxPaths, None, None]:
    """
    Create a fully isolated environment for testing.

    The sandbox is cleaned up automatically after the tests complete.
    """
    root = Path(__file__).parent / "sandbox"
    demo_dir = root / "demo"
    case_dir = root / "cases" / "test"
    outs_dir = root / "outs"

    # CLEAN PREVIOUS INTERRUPTED RUNS IF THEY EXIST
    _cleanup_test_sandbox_roots()

    # CREATE DIRECTORIES
    demo_dir.mkdir(parents=True)
    case_dir.mkdir(parents=True)
    outs_dir.mkdir(parents=True)

    # GENERATE DEMO PROJECT FILES
    # 20-LINE FILE FOR RANGE TESTING
    lines = [f"print('This is line {i}')" for i in range(1, 21)]
    _ = (demo_dir / "app.py").write_text("\n".join(lines), encoding="utf-8")

    # RECURSIVE TRAP FILE (MENTIONS ITSELF AND THE PROJECT)
    _ = (demo_dir / "trap.md").write_text(
        "Look at this loop: <@file:trap.md>\nAnd tree: [@project]", encoding="utf-8"
    )

    # IGNORED FILE
    _ = (demo_dir / "secret.key").write_text("SUPER_SECRET_DATA", encoding="utf-8")

    # .GITIGNORE AND TEST.LOG
    _ = (demo_dir / ".gitignore").write_text("*.log\n", encoding="utf-8")
    _ = (demo_dir / "test.log").write_text("log data", encoding="utf-8")

    # SRC DIR
    src_dir = demo_dir / "src"
    src_dir.mkdir()
    _ = (src_dir / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
    _ = (src_dir / "utils.py").write_text("def util():\n    pass\n", encoding="utf-8")

    # GENERATE CASE CONFIGURATION
    _ = (case_dir / "config.json").write_text(
        '{"name": "test_case", "types": ["*"]}', encoding="utf-8"
    )
    _ = (case_dir / ".caseignore").write_text("*.key\n", encoding="utf-8")
    _ = (case_dir / "system.md").write_text(
        "You are a helpful assistant.", encoding="utf-8"
    )
    _ = (case_dir / "legacy.md").write_text("Analyze: <@file:app.py>", encoding="utf-8")

    yield {"root": root, "demo": demo_dir, "case": case_dir, "outs": outs_dir}

    # TEARDOWN SANDBOX
    _cleanup_test_sandbox_roots()


@pytest.fixture
async def app_components(test_sandbox: SandboxPaths) -> AppComponents:
    """Bootstrap core logic components that point to the dynamic sandbox"""
    case = CaseConfig(test_sandbox["case"])
    indexer = ProjectIndexer(test_sandbox["demo"], case)
    await indexer.build_index()

    context = ProjectContext(test_sandbox["demo"], case, indexer)
    registry = ModRegistry()
    registry.register_defaults()

    resolver = PromptResolver(context, registry)

    return context, resolver


@pytest.fixture(scope="session")
def settings_passes() -> tuple[SettingsPass, ...]:
    """Return the centralized deterministic settings matrix"""
    return build_settings_passes()


def _settings_pass_id(item: SettingsPass) -> str:
    return item.name


@pytest.fixture(params=build_settings_passes(), ids=_settings_pass_id)
def settings_pass(request: FixtureRequest) -> SettingsPass:
    """Iterate through the shared multi-pass settings matrix"""
    return cast(SettingsPass, request.param)


@pytest.fixture
def apply_settings_pass(monkeypatch: MonkeyPatch) -> ApplySettingsPass:
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
            "promptify.ui.editor.runtime",
            "promptify.ui.editor.view",
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

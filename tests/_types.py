"""Shared test-only type aliases for pytest fixtures and helpers"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch

from promptify.core.context import ProjectContext
from promptify.core.resolver import PromptResolver
from promptify.core.settings import AppSettings
from promptify.core.terminal import TerminalProfile

from ._settings_master import SettingsPass


class SandboxPaths(TypedDict):
    """Concrete path mapping returned by the sandbox fixture"""

    root: Path
    demo: Path
    case: Path
    outs: Path


type AppComponents = tuple[ProjectContext, PromptResolver]
type ApplySettingsPass = Callable[
    [SettingsPass], tuple[AppSettings, list[str], TerminalProfile]
]

__all__ = [
    "AppComponents",
    "ApplySettingsPass",
    "FixtureRequest",
    "MonkeyPatch",
    "SandboxPaths",
]

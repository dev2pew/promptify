"""Terminal capability detection and legacy-safe glyph profiles"""

from dataclasses import dataclass
import os
from collections.abc import Mapping

from .settings import APP_SETTINGS


@dataclass(frozen=True, slots=True)
class BorderChars:
    top_left: str
    top_right: str
    bottom_left: str
    bottom_right: str
    horizontal: str
    vertical: str


@dataclass(frozen=True, slots=True)
class TreeChars:
    branch: str
    last_branch: str
    vertical: str
    spacer: str


@dataclass(frozen=True, slots=True)
class TerminalProfile:
    name: str
    supports_unicode: bool
    supports_box_drawing: bool
    supports_mouse: bool
    supports_full_screen: bool
    eof_newline_present: str
    eof_newline_missing: str
    border: BorderChars
    tree: TreeChars


_MODERN_PROFILE = TerminalProfile(
    name="modern",
    supports_unicode=True,
    supports_box_drawing=True,
    supports_mouse=True,
    supports_full_screen=True,
    eof_newline_present="¶",
    eof_newline_missing="∅",
    border=BorderChars("┌", "┐", "└", "┘", "─", "│"),
    tree=TreeChars("├───", "└───", "│   ", "    "),
)

_LEGACY_CMD_PROFILE = TerminalProfile(
    name="legacy-cmd",
    supports_unicode=False,
    supports_box_drawing=False,
    supports_mouse=False,
    supports_full_screen=False,
    eof_newline_present="$",
    eof_newline_missing="!",
    border=BorderChars("+", "+", "+", "+", "-", "|"),
    tree=TreeChars("|---", "`---", "|   ", "    "),
)

_CONHOST_PROFILE = TerminalProfile(
    name="conhost",
    supports_unicode=True,
    supports_box_drawing=True,
    supports_mouse=False,
    supports_full_screen=False,
    eof_newline_present="¶",
    eof_newline_missing="∅",
    border=BorderChars("┌", "┐", "└", "┘", "─", "│"),
    tree=TreeChars("├───", "└───", "│   ", "    "),
)


def _resolve_terminal_kind(env: Mapping[str, str | None], override: str) -> str:
    if override != "auto":
        return override

    term_program = (env.get("TERM_PROGRAM") or "").lower()
    if term_program == "vscode" or env.get("VSCODE_GIT_IPC_HANDLE") is not None:
        return "vscode"
    if env.get("WT_SESSION"):
        return "windows-terminal"

    comspec = (env.get("COMSPEC") or "").lower()
    has_powershell_markers = bool(
        env.get("PSModulePath") or env.get("POWERSHELL_DISTRIBUTION_CHANNEL")
    )
    has_cmd_prompt = bool(env.get("PROMPT"))
    looks_like_windows_console = comspec.endswith("cmd.exe")
    looks_like_windows_env = (
        looks_like_windows_console
        or env.get("WT_SESSION") is not None
        or has_powershell_markers
        or os.name == "nt"
    )

    if looks_like_windows_console and has_cmd_prompt and not has_powershell_markers:
        return "legacy-cmd"

    if looks_like_windows_env:
        return "conhost"
    return "modern"


def detect_terminal_profile(
    env: Mapping[str, str | None] | None = None,
    override: str | None = None,
) -> TerminalProfile:
    """Detect a terminal capability profile with a safe legacy fallback"""
    source_env = os.environ if env is None else env
    chosen = _resolve_terminal_kind(
        source_env,
        APP_SETTINGS.terminal.profile if override is None else override,
    )

    if chosen == "legacy-cmd":
        return _LEGACY_CMD_PROFILE
    if chosen == "conhost":
        return _CONHOST_PROFILE
    return TerminalProfile(
        name=chosen,
        supports_unicode=_MODERN_PROFILE.supports_unicode,
        supports_box_drawing=_MODERN_PROFILE.supports_box_drawing,
        supports_mouse=_MODERN_PROFILE.supports_mouse,
        supports_full_screen=_MODERN_PROFILE.supports_full_screen,
        eof_newline_present=_MODERN_PROFILE.eof_newline_present,
        eof_newline_missing=_MODERN_PROFILE.eof_newline_missing,
        border=_MODERN_PROFILE.border,
        tree=_MODERN_PROFILE.tree,
    )


APP_TERMINAL_PROFILE = detect_terminal_profile()

"""Tests for terminal profile detection and legacy fallbacks"""

from promptify.core.terminal import (
    detect_terminal_profile,
    resolve_prompt_toolkit_surface,
)


def test_detect_terminal_profile_prefers_vscode_markers():
    """VS Code terminals should stay on the modern profile"""
    profile = detect_terminal_profile(
        {"TERM_PROGRAM": "vscode", "COMSPEC": r"C:\Windows\System32\cmd.exe"},
        override="auto",
    )

    assert profile.name == "vscode"
    assert profile.supports_box_drawing
    assert profile.eof_newline_present == "¶"


def test_detect_terminal_profile_falls_back_for_legacy_cmd():
    """Plain cmd sessions should use ASCII-safe chrome"""
    profile = detect_terminal_profile(
        {
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
            "PROMPT": "$P$G",
        },
        override="auto",
    )

    assert profile.name == "legacy-cmd"
    assert not profile.supports_box_drawing
    assert not profile.supports_full_screen
    assert profile.border.top_left == "+"
    assert profile.tree.branch == "|---"


def test_detect_terminal_profile_defaults_to_modern_when_host_is_unclear():
    """Generic Windows shells should keep the editor on the full-screen path"""
    profile = detect_terminal_profile(
        {
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
            "PSModulePath": r"C:\Program Files\PowerShell\Modules",
        },
        override="auto",
    )

    assert profile.name == "modern"
    assert profile.supports_box_drawing
    assert profile.supports_mouse
    assert profile.supports_full_screen


def test_detect_terminal_profile_can_force_safe_conhost_defaults():
    """Explicit conhost mode should still disable prompt-toolkit full-screen"""
    profile = detect_terminal_profile(
        {
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
        },
        override="conhost",
    )

    assert profile.name == "conhost"
    assert profile.supports_box_drawing
    assert not profile.supports_mouse
    assert not profile.supports_full_screen


def test_resolve_prompt_toolkit_surface_respects_terminal_capabilities():
    """Prompt-toolkit surfaces should disable unsupported full-screen and mouse paths"""
    profile = detect_terminal_profile(
        {
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
        },
        override="conhost",
    )

    surface = resolve_prompt_toolkit_surface(
        prefer_full_screen=True,
        prefer_mouse=True,
        profile=profile,
    )

    assert surface.full_screen is False
    assert surface.mouse_support is False


def test_resolve_prompt_toolkit_surface_preserves_supported_flags():
    """Modern profiles should keep requested prompt-toolkit capabilities enabled"""
    profile = detect_terminal_profile(
        {
            "TERM_PROGRAM": "vscode",
        },
        override="auto",
    )

    surface = resolve_prompt_toolkit_surface(
        prefer_full_screen=True,
        prefer_mouse=False,
        profile=profile,
    )

    assert surface.full_screen is True
    assert surface.mouse_support is False

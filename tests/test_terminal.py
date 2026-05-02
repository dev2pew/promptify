"""Tests for terminal profile detection and legacy fallbacks"""

from promptify.core.terminal import detect_terminal_profile


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

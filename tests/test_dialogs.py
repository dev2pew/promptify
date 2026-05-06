"""Tests for prompt-toolkit dialog surfaces used outside the editor"""

from typing import Any

from prompt_toolkit.formatted_text import fragment_list_to_text, to_formatted_text
from prompt_toolkit.widgets import Dialog, Label

from promptify.core.terminal import detect_terminal_profile
from promptify.shared.state import EditorSessionState
from promptify.ui.dialogs import (
    _build_restore_display_item,
    _create_dialog_app,
    _render_restore_session_header,
    _render_restore_session_row,
)


def _as_bool(value: Any) -> bool:
    """Normalize prompt-toolkit filter-like values for assertions"""
    return bool(value() if callable(value) else value)


def test_dialog_app_uses_host_safe_prompt_toolkit_flags(monkeypatch):
    """Classic console dialog apps should avoid unsupported full-screen features"""
    captured: dict[str, Any] = {}
    profile = detect_terminal_profile({}, override="conhost")
    monkeypatch.setattr(
        "promptify.ui.dialogs.terminal_module.APP_TERMINAL_PROFILE", profile
    )
    monkeypatch.setattr(
        "promptify.ui.dialogs.Application",
        lambda **kwargs: captured.update(kwargs) or type("AppStub", (), kwargs)(),
    )

    app = _create_dialog_app(Dialog(title="demo", body=Label(text="body")))

    assert app.full_screen is False
    assert _as_bool(captured["mouse_support"]) is False


def test_restore_session_row_trims_long_target_paths_from_the_left():
    """Restore rows should preserve the most relevant path tail when space is tight"""
    item = _build_restore_display_item(
        EditorSessionState(
            session_id="demo",
            case_dir="C:/cases/my_case",
            target_path="C:/projects/very/long/path/to/the/current/workspace/demo-target",
            prompt_text="",
            updated_at="2026-05-07T05:06:07+00:00",
        )
    )

    fragments = _render_restore_session_row(item, 48)
    text = fragment_list_to_text(to_formatted_text(fragments))

    assert "..." in text
    assert text.rstrip().endswith("workspace/demo-target")
    assert any(style == "class:restore-session.path" for style, *_ in fragments)


def test_restore_session_header_uses_localized_column_titles():
    """The restore-session header should render the three table columns"""
    text = fragment_list_to_text(to_formatted_text(_render_restore_session_header(64)))

    assert "updated" in text
    assert "case" in text
    assert "target" in text

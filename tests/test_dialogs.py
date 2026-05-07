"""Tests for prompt-toolkit dialog surfaces used outside the editor"""

from typing import Any

from prompt_toolkit.formatted_text import fragment_list_to_text, to_formatted_text
from prompt_toolkit.widgets import Dialog, Label, RadioList

from promptify.core.terminal import detect_terminal_profile
from promptify.shared.state import EditorSessionState
from promptify.ui.dialogs import (
    _DialogButton,
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
    assert text.rstrip().endswith("demo-target")
    assert "/" in text or "\\" in text
    assert any(style == "class:restore-session.path" for style, *_ in fragments)


def test_restore_session_header_uses_localized_column_titles():
    """The restore-session header should render the three table columns"""
    text = fragment_list_to_text(to_formatted_text(_render_restore_session_header(64)))

    assert text.startswith(" " * 4)
    assert "updated" in text
    assert "case" in text
    assert "target" in text


def test_restore_session_header_aligns_with_radio_list_content():
    """Header columns should follow the restore-session row layout"""
    item = _build_restore_display_item(
        EditorSessionState(
            session_id="demo",
            case_dir="C:/cases/angular_eq",
            target_path="C:/eq/f",
            prompt_text="",
            updated_at="2026-05-07T02:16:43+00:00",
        )
    )
    width = 80
    header_text = fragment_list_to_text(
        to_formatted_text(_render_restore_session_header(width))
    )
    radio_list = RadioList(
        values=[("demo", lambda: _render_restore_session_row(item, width))],
        default="demo",
    )
    row_text = fragment_list_to_text(radio_list._get_text_fragments()).splitlines()[0]

    assert header_text.index("updated") == row_text.index("2026")
    assert header_text.index("case") == row_text.index("angular_eq") + 1
    assert header_text.index("target") == row_text.index("C:/eq/f") + 1


def test_dialog_button_uses_focused_fragment_classes(monkeypatch):
    """Focused dialog buttons should emit focused text and arrow classes"""
    button = _DialogButton("open")

    class _LayoutStub:
        @staticmethod
        def has_focus(_target: object) -> bool:
            return True

    class _AppStub:
        layout = _LayoutStub()

    monkeypatch.setattr("promptify.ui.dialogs.get_app", lambda: _AppStub())

    fragments = button._get_text_fragments()

    assert any("class:button.focused.arrow" in style for style, *_ in fragments)
    assert any("class:button.focused.text" in style for style, *_ in fragments)

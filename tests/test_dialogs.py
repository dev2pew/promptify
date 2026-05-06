"""Tests for prompt-toolkit dialog surfaces used outside the editor"""

from typing import Any

from prompt_toolkit.widgets import Dialog, Label

from promptify.core.terminal import detect_terminal_profile
from promptify.ui.dialogs import _create_dialog_app


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

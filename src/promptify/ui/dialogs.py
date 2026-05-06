"""Shared prompt-toolkit dialogs for menu-level questions"""

from __future__ import annotations

import functools
from collections.abc import Sequence

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout.containers import HSplit
from prompt_toolkit.layout import Layout
from prompt_toolkit.shortcuts import yes_no_dialog
from prompt_toolkit.widgets import Box, Button, Dialog, Label, RadioList

type SessionRestoreAction = str
type SessionRestoreResult = tuple[SessionRestoreAction, str | None]


def _create_dialog_app(dialog: Dialog) -> Application[object]:
    """Wrap one prompt-toolkit dialog in a full-screen modal application"""
    bindings = KeyBindings()
    bindings.add("tab")(focus_next)
    bindings.add("s-tab")(focus_previous)
    return Application(
        layout=Layout(dialog),
        key_bindings=merge_key_bindings([load_key_bindings(), bindings]),
        mouse_support=True,
        full_screen=True,
    )


async def ask_yes_no_modal(*, title: str, text: str) -> bool:
    """Show a centered yes/no dialog and return the chosen answer"""
    result = await yes_no_dialog(title=title, text=text).run_async()
    return bool(result)


async def ask_restore_session_modal(
    *,
    title: str,
    text: str,
    values: Sequence[tuple[str, str]],
    restore_text: str,
    discard_text: str,
    discard_all_text: str,
    cancel_text: str,
) -> SessionRestoreResult:
    """Show a selectable recovery dialog with restore and discard actions"""
    default = values[0][0] if values else None
    radio_list = RadioList(values=values, default=default)

    def _exit(action: SessionRestoreAction) -> None:
        get_app().exit(result=(action, radio_list.current_value))

    body_items = []
    if text:
        body_items.append(Label(text=text, dont_extend_height=True))
    body_items.append(Box(body=radio_list, padding_top=1 if text else 0))
    dialog = Dialog(
        title=title,
        body=Box(
            body=HSplit(body_items, padding=0),
            padding_left=1,
            padding_right=1,
        ),
        buttons=[
            Button(
                text=restore_text,
                handler=functools.partial(_exit, "restore"),
            ),
            Button(
                text=discard_text,
                handler=functools.partial(_exit, "discard_selected"),
            ),
            Button(
                text=discard_all_text,
                handler=functools.partial(_exit, "discard_all"),
            ),
            Button(
                text=cancel_text,
                handler=functools.partial(_exit, "cancel"),
            ),
        ],
        with_background=True,
    )
    result = await _create_dialog_app(dialog).run_async()
    return result if isinstance(result, tuple) else ("cancel", default)

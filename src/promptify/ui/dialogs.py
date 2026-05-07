"""Shared prompt-toolkit dialogs for menu-level questions"""

from __future__ import annotations

import datetime as dt
import functools
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import promptify.core.terminal as terminal_module

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import Box, Button, Dialog, Label, RadioList

from ..core import settings as settings_module
from ..shared.state import EditorSessionState
from ..utils.i18n import get_string

type SessionRestoreAction = str
type SessionRestoreResult = tuple[SessionRestoreAction, str | None]

_RESTORE_TABLE_SIDE_PADDING = 18
_RESTORE_TABLE_MIN_WIDTH = 32
_RESTORE_UPDATED_WIDTH = 19
_RESTORE_CASE_MIN_WIDTH = 8
_RESTORE_CASE_MAX_WIDTH = 20
_RESTORE_PATH_MIN_WIDTH = 10
_RESTORE_PATH_PREFERRED_WIDTH = 18
_RESTORE_COLUMN_GAP = 3
_RESTORE_SELECTOR_WIDTH = 4


@dataclass(frozen=True, slots=True)
class SessionRestoreDisplayItem:
    """Store the display fields needed by the restore-session picker"""

    session_id: str
    updated: str
    case_name: str
    target_path: str


class _DialogButton(Button):
    """Render dialog buttons with explicit focused and unfocused fragment styles"""

    def _get_text_fragments(self) -> StyleAndTextTuples:
        width = (
            self.width
            - (get_cwidth(self.left_symbol) + get_cwidth(self.right_symbol))
            + (len(self.text) - get_cwidth(self.text))
        )
        text = (f"{{:^{max(0, width)}}}").format(self.text)
        focused = get_app().layout.has_focus(self)
        arrow_style = "class:button.focused.arrow" if focused else "class:button.arrow"
        text_style = "class:button.focused.text" if focused else "class:button.text"

        def handler(mouse_event: MouseEvent) -> None:
            if (
                self.handler is not None
                and mouse_event.event_type == MouseEventType.MOUSE_UP
            ):
                self.handler()

        return [
            (arrow_style, self.left_symbol, handler),
            ("[SetCursorPosition]", ""),
            (text_style, text, handler),
            (arrow_style, self.right_symbol, handler),
        ]


def _build_dialog_style() -> Style:
    """Build prompt-toolkit styles for menu dialogs with safe fallback"""
    try:
        return Style.from_dict(dict(settings_module.APP_SETTINGS.theme.styles))
    except Exception:
        return Style.from_dict({})


def _text_width(text: str) -> int:
    """Measure rendered cell width for one plain-text value"""
    return sum(get_cwidth(ch) for ch in text)


def _trim_text_right(text: str, max_width: int) -> str:
    """Trim from the right while keeping the leading part of a label visible"""
    if max_width <= 0:
        return ""
    if _text_width(text) <= max_width:
        return text
    if max_width <= 3:
        return "." * max_width
    remaining_width = max_width - 3
    kept: list[str] = []
    used_width = 0
    for ch in text:
        ch_width = get_cwidth(ch)
        if used_width + ch_width > remaining_width:
            break
        kept.append(ch)
        used_width += ch_width
    return "".join(kept) + "..."


def _trim_text_left(text: str, max_width: int) -> str:
    """Trim from the left so long paths keep their most relevant tail"""
    if max_width <= 0:
        return ""
    if _text_width(text) <= max_width:
        return text
    if max_width <= 3:
        return "." * max_width
    remaining_width = max_width - 3
    tail: list[str] = []
    used_width = 0
    for ch in reversed(text):
        ch_width = get_cwidth(ch)
        if used_width + ch_width > remaining_width:
            break
        tail.append(ch)
        used_width += ch_width
    tail.reverse()
    return "..." + "".join(tail)


def _pad_text(text: str, width: int) -> str:
    """Pad one table cell to the requested width"""
    padding = max(0, width - _text_width(text))
    return text + (" " * padding)


def _format_restore_timestamp(timestamp: str) -> str:
    """Normalize one saved-session timestamp for table display"""
    try:
        parsed = dt.datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.UTC)
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return timestamp


def _build_restore_display_item(
    session: EditorSessionState,
) -> SessionRestoreDisplayItem:
    """Convert one saved session into the fields rendered by the dialog table"""
    return SessionRestoreDisplayItem(
        session_id=session.session_id,
        updated=_format_restore_timestamp(session.updated_at),
        case_name=Path(session.case_dir).name or session.case_dir,
        target_path=session.target_path,
    )


def _restore_table_width() -> int:
    """Estimate a safe table width from the current prompt-toolkit output size"""
    fallback = settings_module.APP_SETTINGS.render.terminal_fallback_width
    try:
        columns = get_app().output.get_size().columns
    except Exception:
        columns = fallback
    return max(_RESTORE_TABLE_MIN_WIDTH, columns - _RESTORE_TABLE_SIDE_PADDING)


def _restore_column_widths(total_width: int) -> tuple[int, int, int]:
    """Split the table width across updated, case, and target columns"""
    if total_width <= _RESTORE_UPDATED_WIDTH:
        return total_width, 0, 0
    two_column_path_width = total_width - _RESTORE_UPDATED_WIDTH - _RESTORE_COLUMN_GAP
    if two_column_path_width <= _RESTORE_PATH_MIN_WIDTH:
        return _RESTORE_UPDATED_WIDTH, 0, max(0, two_column_path_width)

    remaining = max(0, total_width - _RESTORE_UPDATED_WIDTH - (_RESTORE_COLUMN_GAP * 2))
    if remaining < _RESTORE_CASE_MIN_WIDTH + _RESTORE_PATH_PREFERRED_WIDTH:
        return _RESTORE_UPDATED_WIDTH, 0, two_column_path_width

    case_width = min(
        _RESTORE_CASE_MAX_WIDTH,
        max(_RESTORE_CASE_MIN_WIDTH, remaining // 3),
    )
    path_width = remaining - case_width
    if path_width < _RESTORE_PATH_MIN_WIDTH:
        deficit = _RESTORE_PATH_MIN_WIDTH - path_width
        case_width = max(_RESTORE_CASE_MIN_WIDTH, case_width - deficit)
        path_width = remaining - case_width
    return _RESTORE_UPDATED_WIDTH, case_width, max(_RESTORE_PATH_MIN_WIDTH, path_width)


def _restore_table_content_width(total_width: int) -> int:
    """Return the usable width for table text after the radio selector prefix"""
    return max(0, total_width - _RESTORE_SELECTOR_WIDTH)


def _render_restore_session_header(total_width: int) -> StyleAndTextTuples:
    """Render the restore-session column header"""
    content_width = _restore_table_content_width(total_width)
    updated_width, case_width, path_width = _restore_column_widths(content_width)
    fragments: StyleAndTextTuples = [
        ("class:restore-session.header", " " * _RESTORE_SELECTOR_WIDTH),
        (
            "class:restore-session.header",
            _pad_text(
                _trim_text_right(
                    get_string("restore_session_header_updated", "updated"),
                    updated_width,
                ),
                updated_width,
            ),
        ),
    ]
    if case_width > 0:
        fragments.extend(
            [
                ("class:restore-session.header", "  | "),
                (
                    "class:restore-session.header",
                    _pad_text(
                        _trim_text_right(
                            get_string("restore_session_header_case", "case"),
                            case_width,
                        ),
                        case_width,
                    ),
                ),
            ]
        )
    if path_width > 0:
        fragments.extend(
            [
                ("class:restore-session.header", " | "),
                (
                    "class:restore-session.header",
                    _pad_text(
                        _trim_text_right(
                            get_string("restore_session_header_target", "target"),
                            path_width,
                        ),
                        path_width,
                    ),
                ),
            ]
        )
    return fragments


def _render_restore_session_row(
    item: SessionRestoreDisplayItem, total_width: int
) -> StyleAndTextTuples:
    """Render one restore-session row with width-aware truncation"""
    content_width = _restore_table_content_width(total_width)
    updated_width, case_width, path_width = _restore_column_widths(content_width)
    fragments: StyleAndTextTuples = [
        (
            "class:restore-session.timestamp",
            _pad_text(_trim_text_right(item.updated, updated_width), updated_width),
        )
    ]
    if case_width > 0:
        fragments.extend(
            [
                ("class:restore-session.separator", " | "),
                (
                    "class:restore-session.case",
                    _pad_text(
                        _trim_text_right(item.case_name, case_width),
                        case_width,
                    ),
                ),
            ]
        )
    if path_width > 0:
        fragments.extend(
            [
                ("class:restore-session.separator", " | "),
                (
                    "class:restore-session.path",
                    _pad_text(
                        _trim_text_left(item.target_path, path_width),
                        path_width,
                    ),
                ),
            ]
        )
    return fragments


def _create_dialog_app(dialog: Dialog) -> Application[object]:
    """Wrap one prompt-toolkit dialog in a full-screen modal application"""
    bindings = KeyBindings()
    bindings.add("tab")(focus_next)
    bindings.add("s-tab")(focus_previous)
    surface = terminal_module.resolve_prompt_toolkit_surface(prefer_full_screen=True)
    return Application(
        layout=Layout(dialog),
        key_bindings=merge_key_bindings([load_key_bindings(), bindings]),
        mouse_support=surface.mouse_support,
        full_screen=surface.full_screen,
        style=_build_dialog_style(),
    )


async def ask_yes_no_modal(*, title: str, text: str) -> bool:
    """Show a centered yes/no dialog and return the chosen answer"""

    def _exit(result: bool) -> None:
        get_app().exit(result=result)

    dialog = Dialog(
        title=title,
        body=Box(body=Label(text=text, dont_extend_height=True), padding=1),
        buttons=[
            _DialogButton(
                text=get_string("yes_option", "yes"),
                handler=functools.partial(_exit, True),
            ),
            _DialogButton(
                text=get_string("no_option", "no"),
                handler=functools.partial(_exit, False),
            ),
        ],
        with_background=True,
    )
    result = await _create_dialog_app(dialog).run_async()
    return bool(result)


async def ask_restore_session_modal(
    *,
    title: str,
    text: str,
    sessions: Sequence[EditorSessionState],
    restore_text: str,
    discard_text: str,
    discard_all_text: str,
    cancel_text: str,
) -> SessionRestoreResult:
    """Show a selectable recovery dialog with restore and discard actions"""
    items = tuple(_build_restore_display_item(session) for session in sessions)
    values = [
        (
            item.session_id,
            lambda item=item: _render_restore_session_row(item, _restore_table_width()),
        )
        for item in items
    ]
    default = values[0][0] if values else None
    radio_list = RadioList(values=values, default=default)

    def _exit(action: SessionRestoreAction) -> None:
        get_app().exit(result=(action, radio_list.current_value))

    body_items = []
    if text:
        body_items.append(Label(text=text, dont_extend_height=True))
    body_items.append(
        Window(
            content=FormattedTextControl(
                lambda: _render_restore_session_header(_restore_table_width())
            ),
            dont_extend_height=True,
        )
    )
    body_items.append(Box(body=radio_list, padding_top=0))
    dialog = Dialog(
        title=title,
        body=Box(
            body=HSplit(body_items, padding=0),
            padding_left=1,
            padding_right=1,
        ),
        buttons=[
            _DialogButton(
                text=restore_text,
                handler=functools.partial(_exit, "restore"),
            ),
            _DialogButton(
                text=discard_text,
                handler=functools.partial(_exit, "discard_selected"),
            ),
            _DialogButton(
                text=discard_all_text,
                handler=functools.partial(_exit, "discard_all"),
            ),
            _DialogButton(
                text=cancel_text,
                handler=functools.partial(_exit, "cancel"),
            ),
        ],
        with_background=True,
    )
    result = await _create_dialog_app(dialog).run_async()
    return result if isinstance(result, tuple) else ("cancel", default)

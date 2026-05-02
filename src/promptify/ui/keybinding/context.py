"""Shared context and helpers for editor keybinding registration"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters.base import Filter, FilterOrBool
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys

from ...shared.editor_state import EditorIssue, OverlayName

type BindingHandler = Callable[[KeyPressEvent], None]
type IndentDetector = Callable[[Document], str]
type HomePositionGetter = Callable[[Document], int]
type SelectionStarter = Callable[[Buffer], None]
type PasteScheduler = Callable[[], None]


class EditorBindingHost(Protocol):
    """Minimal editor surface needed by the binding registration helpers."""

    help_visible: bool
    err_visible: bool
    issue_mode_active: bool
    quit_visible: bool
    replace_visible: bool
    buffer: Buffer
    search_buffer: Buffer
    replace_buffer: Buffer
    jump_buffer: Buffer
    result: str | None

    def note_user_activity(self) -> None: ...

    def set_passive_status(self, message: str, transient: bool = True) -> None: ...

    def get_text(self, key: str, default: str) -> str: ...

    def paste_text(self, buffer: Buffer, text: str) -> None: ...

    def toggle_help(self) -> None: ...

    def open_search(self) -> None: ...

    def toggle_replace(self) -> None: ...

    def open_jump(self) -> None: ...

    def toggle_word_wrap(self) -> None: ...

    def close_help(self) -> None: ...

    def deactivate_issue_mode(self) -> None: ...

    def _hide_overlay(
        self, overlay: OverlayName, *, restore_view: bool = False
    ) -> None: ...

    def step_issue(self, direction: int) -> bool: ...

    def confirm_quit(self) -> None: ...

    def close_quit_confirm(self) -> None: ...

    def close_search(self) -> None: ...

    def search_step(self, direction: int) -> bool: ...

    def cycle_search_history(self, direction: int) -> None: ...

    def toggle_match_case(self) -> None: ...

    def toggle_match_whole_word(self) -> None: ...

    def toggle_regex(self) -> None: ...

    def toggle_preserve_case(self) -> None: ...

    def replace_current(self) -> bool: ...

    def replace_all(self) -> int: ...

    def close_jump(self) -> None: ...

    def submit_jump(self) -> bool: ...

    async def collect_save_issues(self) -> tuple[EditorIssue, ...]: ...

    def activate_issue_mode(self, issues: tuple[EditorIssue, ...]) -> None: ...

    def open_quit_confirm(self) -> None: ...


@dataclass(slots=True)
class EditorBindingContext:
    """Bundle shared editor state, filters, and helpers for binding modules"""

    editor: EditorBindingHost
    bindings: KeyBindings
    editor_focus: Filter
    search_focus: Filter
    replace_focus: Filter
    jump_focus: Filter
    search_widget_focus: Filter
    text_focus: Filter
    is_help_visible: Filter
    is_err_visible: Filter
    is_issue_mode_active: Filter
    is_quit_visible: Filter
    is_replace_visible: Filter
    has_completions_menu: Filter
    is_completion_selected: Filter
    detect_indent_style: IndentDetector
    get_home_position: HomePositionGetter
    start_selection: SelectionStarter
    schedule_system_clipboard_paste: PasteScheduler

    def bind(
        self,
        *keys: Keys | str,
        filter: FilterOrBool = True,
        eager: bool = False,
        note_activity: bool = False,
        invalidate: bool = False,
    ) -> Callable[[BindingHandler], BindingHandler]:
        """Register one binding while handling common editor bookkeeping"""

        def decorator(handler: BindingHandler) -> BindingHandler:
            def wrapped(event: KeyPressEvent) -> None:
                if note_activity:
                    self.editor.note_user_activity()
                handler(event)
                if invalidate:
                    event.app.invalidate()

            _ = self.bindings.add(*keys, filter=filter, eager=eager)(wrapped)
            return handler

        return decorator

"""Shared context and helpers for editor keybinding registration"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters.base import FilterOrBool
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent

if TYPE_CHECKING:
    from ..editor import InteractiveEditor

type BindingHandler = Callable[[KeyPressEvent], None]
type IndentDetector = Callable[[Document], str]
type HomePositionGetter = Callable[[Document], int]
type SelectionStarter = Callable[[Buffer], None]
type PasteScheduler = Callable[[], None]


@dataclass(slots=True)
class EditorBindingContext:
    """Bundle shared editor state, filters, and helpers for binding modules"""

    editor: InteractiveEditor
    bindings: KeyBindings
    editor_focus: FilterOrBool
    search_focus: FilterOrBool
    replace_focus: FilterOrBool
    jump_focus: FilterOrBool
    search_widget_focus: FilterOrBool
    text_focus: FilterOrBool
    is_help_visible: FilterOrBool
    is_err_visible: FilterOrBool
    is_issue_mode_active: FilterOrBool
    is_quit_visible: FilterOrBool
    is_replace_visible: FilterOrBool
    has_completions_menu: FilterOrBool
    is_completion_selected: FilterOrBool
    detect_indent_style: IndentDetector
    get_home_position: HomePositionGetter
    start_selection: SelectionStarter
    schedule_system_clipboard_paste: PasteScheduler

    def bind(
        self,
        *keys: object,
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

            self.bindings.add(*keys, filter=filter, eager=eager)(wrapped)
            return handler

        return decorator

"""Shared context and helpers for editor keybinding registration"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters.base import Filter, FilterOrBool
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys

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

            self.bindings.add(*keys, filter=filter, eager=eager)(wrapped)
            return handler

        return decorator

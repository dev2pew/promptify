"""Editor-specific prompt-toolkit controls"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import BufferControl, UIContent
from prompt_toolkit.mouse_events import MouseEventType


class EditorBuffer(Buffer):
    """Buffer with a bounded undo and redo history"""

    def __init__(self, *args: Any, undo_limit: int = 256, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._undo_limit = max(1, undo_limit)

    def _trim_history(self) -> None:
        """Keep prompt-toolkit undo and redo stacks within the configured limit"""
        if len(self._undo_stack) > self._undo_limit:
            del self._undo_stack[: len(self._undo_stack) - self._undo_limit]
        if len(self._redo_stack) > self._undo_limit:
            del self._redo_stack[: len(self._redo_stack) - self._undo_limit]

    def save_to_undo_stack(self, clear_redo_stack: bool = True) -> None:
        """Save one undo snapshot and trim both history stacks afterward"""
        super().save_to_undo_stack(clear_redo_stack=clear_redo_stack)
        self._trim_history()


class EditorBufferControl(BufferControl):
    """Clear cloned cursors before mouse-driven caret changes"""

    def __init__(self, *args, on_mouse_down=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_mouse_down = on_mouse_down

    def mouse_handler(self, mouse_event):
        if (
            self._on_mouse_down is not None
            and mouse_event.event_type == MouseEventType.MOUSE_DOWN
        ):
            self._on_mouse_down()
        return super().mouse_handler(mouse_event)


class EditorWindow(Window):
    """Window that can keep a manually scrolled viewport detached from the caret"""

    def __init__(
        self,
        *args: Any,
        get_detached_vertical_scroll: Callable[[], int | None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._get_detached_vertical_scroll = get_detached_vertical_scroll

    def _scroll(self, ui_content: UIContent, width: int, height: int) -> None:
        super()._scroll(ui_content, width, height)
        if self._get_detached_vertical_scroll is None:
            return
        detached_scroll = self._get_detached_vertical_scroll()
        if detached_scroll is None:
            return
        max_scroll = max(0, ui_content.line_count - max(1, height))
        self.vertical_scroll = max(0, min(max_scroll, detached_scroll))
        self.vertical_scroll_2 = 0

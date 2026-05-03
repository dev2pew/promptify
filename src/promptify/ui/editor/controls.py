"""Editor-specific prompt-toolkit controls"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import BufferControl, UIContent
from prompt_toolkit.mouse_events import MouseEventType


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
    """Window that can keep a manually scrolled viewport detached from the caret."""

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

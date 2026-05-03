"""Editor-specific prompt-toolkit controls"""

from __future__ import annotations

from prompt_toolkit.layout.controls import BufferControl
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

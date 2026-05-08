"""Editor-specific prompt-toolkit controls"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import BufferControl, UIContent
from prompt_toolkit.mouse_events import MouseEventType

from ...shared.editor_state import EditorHistorySnapshot


type HistorySnapshotGetter = Callable[[], EditorHistorySnapshot | None]
type HistorySnapshotRestorer = Callable[[EditorHistorySnapshot | None], None]


class EditorBuffer(Buffer):
    """Buffer with a bounded undo and redo history"""

    def __init__(
        self,
        *args: Any,
        undo_limit: int = 256,
        history_snapshot_getter: HistorySnapshotGetter | None = None,
        history_snapshot_restorer: HistorySnapshotRestorer | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._undo_limit = max(1, undo_limit)
        self._history_snapshot_getter = history_snapshot_getter
        self._history_snapshot_restorer = history_snapshot_restorer
        self._undo_history_snapshots: list[EditorHistorySnapshot | None] = []
        self._redo_history_snapshots: list[EditorHistorySnapshot | None] = []

    def _capture_history_snapshot(self) -> EditorHistorySnapshot | None:
        """Read the editor-side state that should stay aligned with buffer history"""
        if self._history_snapshot_getter is None:
            return None
        return self._history_snapshot_getter()

    def _restore_history_snapshot(self, snapshot: EditorHistorySnapshot | None) -> None:
        """Restore editor-side caret state after a prompt-toolkit history jump"""
        if self._history_snapshot_restorer is None:
            return
        self._history_snapshot_restorer(snapshot)

    def _trim_history(self) -> None:
        """Keep prompt-toolkit undo and redo stacks within the configured limit"""
        if len(self._undo_stack) > self._undo_limit:
            del self._undo_stack[: len(self._undo_stack) - self._undo_limit]
            del self._undo_history_snapshots[
                : len(self._undo_history_snapshots) - self._undo_limit
            ]
        if len(self._redo_stack) > self._undo_limit:
            del self._redo_stack[: len(self._redo_stack) - self._undo_limit]
            del self._redo_history_snapshots[
                : len(self._redo_history_snapshots) - self._undo_limit
            ]

    def save_to_undo_stack(self, clear_redo_stack: bool = True) -> None:
        """Save one undo snapshot and trim both history stacks afterward"""
        snapshot = self._capture_history_snapshot()
        if self._undo_stack and self._undo_stack[-1][0] == self.text:
            self._undo_stack[-1] = (self._undo_stack[-1][0], self.cursor_position)
            if self._undo_history_snapshots:
                self._undo_history_snapshots[-1] = snapshot
            else:
                self._undo_history_snapshots.append(snapshot)
        else:
            self._undo_stack.append((self.text, self.cursor_position))
            self._undo_history_snapshots.append(snapshot)

        if clear_redo_stack:
            self._redo_stack = []
            self._redo_history_snapshots = []
        self._trim_history()

    def undo(self) -> None:
        """Undo text while restoring the matching editor caret snapshot"""
        while self._undo_stack:
            text, pos = self._undo_stack.pop()
            snapshot = (
                self._undo_history_snapshots.pop()
                if self._undo_history_snapshots
                else None
            )

            if text != self.text:
                self._redo_stack.append((self.text, self.cursor_position))
                self._redo_history_snapshots.append(self._capture_history_snapshot())
                self.document = Document(text, cursor_position=pos)
                self._restore_history_snapshot(snapshot)
                self._trim_history()
                break

    def redo(self) -> None:
        """Redo text while restoring the matching editor caret snapshot"""
        if not self._redo_stack:
            return
        self.save_to_undo_stack(clear_redo_stack=False)
        text, pos = self._redo_stack.pop()
        snapshot = (
            self._redo_history_snapshots.pop() if self._redo_history_snapshots else None
        )
        self.document = Document(text, cursor_position=pos)
        self._restore_history_snapshot(snapshot)


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

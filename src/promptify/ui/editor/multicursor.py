"""Multi-caret state and editing helpers for the interactive editor"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from prompt_toolkit.selection import SelectionState

from ...shared.editor_state import (
    EditorCaretTarget,
    EditorTextEdit,
    MultiCursorCaret,
    SearchOptions,
)
from ...shared.editor_support import (
    get_editor_closing_wrap_rule,
    get_editor_wrap_rule,
    get_logical_line_span,
    get_visual_line_targets,
    get_visual_vertical_target,
    apply_editor_text_edits,
)
from ._imports import Document, Window
from .controls import EditorBuffer

_KEEP_ANCHOR = object()


class EditorMultiCursorMixin:
    """Provide VS Code-style sticky-column and multi-cursor editing behavior"""

    _multi_carets: list[MultiCursorCaret] = []
    _multi_cursor_owned_search: bool = False
    _multi_cursor_occurrence_query: str = ""
    _multi_cursor_last_vertical_direction: int = 0
    _wrap_preferred_column: int | None = None
    _detached_vertical_scroll: int | None = None
    _internal_clipboard_text: str = ""
    buffer: EditorBuffer = cast(EditorBuffer, cast(object, None))
    search_buffer: EditorBuffer = cast(EditorBuffer, cast(object, None))
    main_window: Window = cast(Window, cast(object, None))
    search_visible: bool = False
    replace_visible: bool = False
    word_wrap_enabled: bool = False
    search_options: SearchOptions = SearchOptions()

    if TYPE_CHECKING:

        def invalidate(self) -> None: ...

        def _focus_main(self) -> None: ...

        def note_user_activity(self) -> None: ...

        def start_bulk_edit(self, inserted_text: str) -> None: ...

    def _make_primary_caret(self) -> MultiCursorCaret:
        """Capture the live primary cursor into the virtual caret model"""
        return MultiCursorCaret(
            position=self.buffer.cursor_position,
            anchor=None,
            preferred_column=self.buffer.preferred_column,
            visual_column=self._wrap_preferred_column,
            is_primary=True,
        )

    def _get_multi_carets(self) -> tuple[MultiCursorCaret, ...]:
        """Return the active virtual carets or a single live primary caret"""
        if self._multi_carets:
            return tuple(self._multi_carets)
        return (self._make_primary_caret(),)

    def _primary_selection_caret(self) -> MultiCursorCaret | None:
        """Reflect the live prompt-toolkit selection as one editable caret"""
        selection = self.buffer.selection_state
        if selection is None:
            return None
        if selection.original_cursor_position == self.buffer.cursor_position:
            return None
        return MultiCursorCaret(
            position=self.buffer.cursor_position,
            anchor=selection.original_cursor_position,
            preferred_column=self.buffer.preferred_column,
            visual_column=self._wrap_preferred_column,
            is_primary=True,
        )

    def _get_edit_carets(self) -> tuple[MultiCursorCaret, ...]:
        """Return edit carets, including a plain primary selection when present"""
        if self._multi_carets:
            return tuple(self._multi_carets)
        selected = self._primary_selection_caret()
        if selected is not None:
            return (selected,)
        return (self._make_primary_caret(),)

    def _caret_target(
        self,
        caret: MultiCursorCaret,
        *,
        source_position: int | None = None,
        replacement_offset: int = 0,
        anchor_source_position: int | None | object = _KEEP_ANCHOR,
        anchor_replacement_offset: int = 0,
    ) -> EditorCaretTarget:
        """Build one caret target while preserving primary and column metadata"""
        source = caret.position if source_position is None else source_position
        anchor_source: int | None
        if anchor_source_position is _KEEP_ANCHOR:
            anchor_source = caret.anchor
        else:
            anchor_source = cast(int | None, anchor_source_position)
        return EditorCaretTarget(
            source_position=source,
            replacement_offset=replacement_offset,
            anchor_source_position=anchor_source,
            anchor_replacement_offset=anchor_replacement_offset,
            preferred_column=caret.preferred_column,
            visual_column=caret.visual_column,
            is_primary=caret.is_primary,
        )

    def _merge_text_edit(
        self,
        edits: list[EditorTextEdit],
        indexes: dict[tuple[int, int, str], int],
        *,
        start: int,
        end: int,
        replacement: str,
        carets: Sequence[EditorCaretTarget],
    ) -> None:
        """Merge equivalent edits so one insertion can keep multiple caret targets"""
        key = (start, end, replacement)
        edit_carets = tuple(carets)
        existing_index = indexes.get(key)
        if existing_index is None:
            indexes[key] = len(edits)
            edits.append(
                EditorTextEdit(
                    start=start,
                    end=end,
                    replacement=replacement,
                    carets=edit_carets,
                )
            )
            return
        existing = edits[existing_index]
        edits[existing_index] = EditorTextEdit(
            start=existing.start,
            end=existing.end,
            replacement=existing.replacement,
            carets=existing.carets + edit_carets,
        )

    def reset_cursor_navigation_memory(self) -> None:
        """Clear sticky visual and logical columns after non-vertical navigation"""
        self._wrap_preferred_column = None
        self.buffer.preferred_column = None

    def reattach_scroll_to_cursor(self) -> None:
        """Let prompt-toolkit keep the viewport tied to the caret again"""
        self._detached_vertical_scroll = None

    def get_detached_vertical_scroll(self) -> int | None:
        """Return a manual viewport offset while view-only scrolling is active"""
        return self._detached_vertical_scroll

    def multi_cursor_active(self) -> bool:
        """Return whether extra virtual carets or selections are active"""
        return any(
            caret.is_primary is False or caret.has_selection
            for caret in self._get_multi_carets()
        )

    def _clamp_multi_caret(
        self, caret: MultiCursorCaret, *, primary_claimed: bool
    ) -> MultiCursorCaret:
        """Return one caret clamped to the live document bounds"""
        text_length = len(self.buffer.text)
        position = max(0, min(text_length, caret.position))
        anchor = (
            None if caret.anchor is None else max(0, min(text_length, caret.anchor))
        )
        return MultiCursorCaret(
            position=position,
            anchor=anchor,
            preferred_column=caret.preferred_column,
            visual_column=caret.visual_column,
            is_primary=caret.is_primary and not primary_claimed,
        )

    def _merge_two_carets(
        self, previous: MultiCursorCaret, current: MultiCursorCaret
    ) -> MultiCursorCaret:
        """Merge overlapping edit ranges into one non-conflicting caret"""
        start = min(previous.selection_start, current.selection_start)
        end = max(previous.selection_end, current.selection_end)
        is_primary = previous.is_primary or current.is_primary
        preferred_column = (
            current.preferred_column
            if current.is_primary and current.preferred_column is not None
            else previous.preferred_column
        )
        visual_column = (
            current.visual_column
            if current.is_primary and current.visual_column is not None
            else previous.visual_column
        )
        return MultiCursorCaret(
            position=end,
            anchor=start if start != end else None,
            preferred_column=preferred_column,
            visual_column=visual_column,
            is_primary=is_primary,
        )

    def _merge_multi_carets(
        self, carets: list[MultiCursorCaret]
    ) -> list[MultiCursorCaret]:
        """Normalize carets into non-overlapping edit ranges with one primary"""
        primary_claimed = False
        clamped: list[MultiCursorCaret] = []
        for caret in carets:
            normalized = self._clamp_multi_caret(caret, primary_claimed=primary_claimed)
            primary_claimed = primary_claimed or normalized.is_primary
            clamped.append(normalized)

        if not clamped:
            clamped.append(self._make_primary_caret())

        ordered = sorted(
            clamped,
            key=lambda caret: (
                caret.selection_start,
                caret.selection_end,
                caret.position,
                not caret.is_primary,
            ),
        )
        merged: list[MultiCursorCaret] = []
        for caret in ordered:
            if not merged:
                merged.append(caret)
                continue

            previous = merged[-1]
            same_collapsed_position = (
                not previous.has_selection
                and not caret.has_selection
                and previous.position == caret.position
            )
            overlaps_previous_range = (
                previous.selection_start
                <= caret.selection_start
                < previous.selection_end
                or caret.selection_start
                <= previous.selection_start
                < caret.selection_end
            )
            if same_collapsed_position or overlaps_previous_range:
                merged[-1] = self._merge_two_carets(previous, caret)
            else:
                merged.append(caret)

        if not any(caret.is_primary for caret in merged):
            live_position = self._make_primary_caret().position
            nearest_index = min(
                range(len(merged)),
                key=lambda index: abs(merged[index].position - live_position),
            )
            merged[nearest_index].is_primary = True
        return merged

    def _set_multi_carets(self, carets: list[MultiCursorCaret]) -> None:
        """Persist the virtual carets and sync the real prompt-toolkit cursor"""
        merged = self._merge_multi_carets(carets)
        primary = next(caret for caret in merged if caret.is_primary)
        self._multi_carets = merged
        self.buffer.selection_state = None
        self.buffer.cursor_position = primary.position
        self.buffer.preferred_column = primary.preferred_column
        self._wrap_preferred_column = primary.visual_column
        self.invalidate()

    def clear_multi_cursors(self) -> None:
        """Remove all virtual carets and restore the single real cursor"""
        self._multi_carets = []
        self._multi_cursor_occurrence_query = ""
        self._multi_cursor_last_vertical_direction = 0
        self._wrap_preferred_column = None
        if self._multi_cursor_owned_search:
            self.search_visible = False
            self.replace_visible = False
            self._multi_cursor_owned_search = False
            self._focus_main()
        self.buffer.selection_state = None
        self.buffer.preferred_column = None
        self.invalidate()

    def occurrence_mode_active(self) -> bool:
        """Return whether Ctrl+D occurrence selection mode is active"""
        return bool(self._multi_cursor_occurrence_query)

    def set_internal_clipboard_text(self, text: str) -> None:
        """Store editor clipboard text independently from the system clipboard"""
        self._internal_clipboard_text = text

    def get_internal_clipboard_text(self) -> str:
        """Return the last text copied or cut inside this editor instance"""
        return self._internal_clipboard_text

    def reset_multi_cursors_for_mouse(self) -> None:
        """Drop cloned carets before a mouse click repositions the real cursor"""
        if self.multi_cursor_active():
            self.clear_multi_cursors()

    def _show_multi_cursor_search(self, query: str) -> None:
        """Seed the search query used by occurrence selection without stealing focus"""
        self.search_buffer.document = Document(query, cursor_position=len(query))
        self.invalidate()

    def _current_word_range(self) -> tuple[int, int] | None:
        """Return the current word boundaries for Ctrl+D when no text is selected"""
        start_offset, end_offset = (
            self.buffer.document.find_boundaries_of_current_word()
        )
        if start_offset == 0 and end_offset == 0:
            return None
        start = self.buffer.cursor_position + start_offset
        end = self.buffer.cursor_position + end_offset
        if start == end:
            return None
        return start, end

    def _compile_occurrence_pattern(self, query: str) -> re.Pattern[str]:
        """Compile literal next-occurrence matching using the live search toggles"""
        body = re.escape(query)
        if getattr(self.search_options, "match_whole_word", False):
            body = rf"\b(?:{body})\b"
        flags = (
            0 if getattr(self.search_options, "match_case", False) else re.IGNORECASE
        )
        return re.compile(body, flags)

    def _find_occurrence_ranges(self, query: str) -> tuple[tuple[int, int], ...]:
        """Find all literal occurrence ranges that match the live search toggles"""
        if not query:
            return tuple()
        pattern = self._compile_occurrence_pattern(query)
        return tuple(
            (match.start(), match.end())
            for match in pattern.finditer(self.buffer.text)
            if match.start() != match.end()
        )

    def _resolve_occurrence_seed(self) -> tuple[str, tuple[int, int]] | None:
        """Resolve the query and primary range for Ctrl+D or Ctrl+Shift+L"""
        carets = self._get_multi_carets()
        primary = next(caret for caret in carets if caret.is_primary)
        if primary.has_selection:
            query = self.buffer.text[primary.selection_start : primary.selection_end]
            return query, (primary.selection_start, primary.selection_end)
        current_range = self._current_word_range()
        if current_range is None:
            return None
        query = self.buffer.text[current_range[0] : current_range[1]]
        return query, current_range

    def select_next_occurrence(self) -> bool:
        """Select the next literal occurrence using the live search toggles"""
        seed = self._resolve_occurrence_seed()
        if seed is None:
            return False
        query, primary_range = seed
        all_ranges = self._find_occurrence_ranges(query)
        if not all_ranges:
            return False
        carets = list(self._get_multi_carets())
        primary = next(caret for caret in carets if caret.is_primary)
        if not primary.has_selection:
            primary.anchor = primary_range[0]
            primary.position = primary_range[1]
            self._multi_cursor_occurrence_query = query
            self._show_multi_cursor_search(query)
            self._set_multi_carets(carets)
            return True

        selected = {caret.range_key for caret in carets}
        ordered_ranges = list(all_ranges)
        start_index = 0
        if primary.range_key in selected and primary.range_key in ordered_ranges:
            start_index = ordered_ranges.index(primary.range_key) + 1
        for offset in range(len(ordered_ranges)):
            start, end = ordered_ranges[(start_index + offset) % len(ordered_ranges)]
            if (start, end) in selected:
                continue
            carets.append(MultiCursorCaret(position=end, anchor=start))
            self._multi_cursor_occurrence_query = query
            self._show_multi_cursor_search(query)
            self._set_multi_carets(carets)
            return True
        return False

    def select_all_occurrences(self) -> bool:
        """Select every literal occurrence of the current selection or word"""
        seed = self._resolve_occurrence_seed()
        if seed is None:
            return False
        query, primary_range = seed
        all_ranges = self._find_occurrence_ranges(query)
        if not all_ranges:
            return False
        carets: list[MultiCursorCaret] = []
        for start, end in all_ranges:
            carets.append(
                MultiCursorCaret(
                    position=end,
                    anchor=start,
                    is_primary=(start, end) == primary_range,
                )
            )
        if not any(caret.is_primary for caret in carets):
            carets[0].is_primary = True
        self._multi_cursor_occurrence_query = query
        self._show_multi_cursor_search(query)
        self._set_multi_carets(carets)
        return True

    def _move_logical_vertical_caret(
        self, caret: MultiCursorCaret, direction: int, *, count: int = 1
    ) -> MultiCursorCaret:
        """Move one caret by logical lines while keeping its preferred column"""
        document = Document(self.buffer.text, cursor_position=caret.position)
        preferred = (
            caret.preferred_column
            if caret.preferred_column is not None
            else document.cursor_position_col
        )
        delta = (
            document.get_cursor_down_position(count=count, preferred_column=preferred)
            if direction > 0
            else document.get_cursor_up_position(
                count=count, preferred_column=preferred
            )
        )
        return MultiCursorCaret(
            position=max(0, min(len(self.buffer.text), caret.position + delta)),
            anchor=None,
            preferred_column=preferred,
            visual_column=None,
            is_primary=caret.is_primary,
        )

    def _move_visual_vertical_caret_once(
        self, caret: MultiCursorCaret, direction: int
    ) -> MultiCursorCaret | None:
        """Move one caret through wrapped visual rows when render data is available"""
        render_info = self.main_window.render_info
        if (
            render_info is None
            or not self.word_wrap_enabled
            or not getattr(render_info, "wrap_lines", False)
        ):
            return None

        visual_column = (
            self._wrap_preferred_column
            if caret.is_primary and not self.multi_cursor_active()
            else caret.visual_column
        )
        target = get_visual_vertical_target(
            self.buffer.text,
            caret.position,
            render_info,
            direction=direction,
            preferred_column=visual_column,
        )
        if target is None:
            return None
        target_position, visual_column = target
        target_document = Document(self.buffer.text, cursor_position=target_position)
        _target_row, target_col = target_document.translate_index_to_position(
            target_position
        )

        if caret.is_primary and not self.multi_cursor_active():
            self._wrap_preferred_column = visual_column
        return MultiCursorCaret(
            position=target_position,
            anchor=None,
            preferred_column=target_col,
            visual_column=visual_column,
            is_primary=caret.is_primary,
        )

    def _move_vertical_caret(
        self, caret: MultiCursorCaret, direction: int, *, count: int = 1
    ) -> MultiCursorCaret:
        """Move one caret vertically, preferring visual rows while wrapped"""
        moved = caret
        for remaining in range(count, 0, -1):
            visual = self._move_visual_vertical_caret_once(moved, direction)
            if visual is None:
                self._wrap_preferred_column = None
                return self._move_logical_vertical_caret(
                    moved, direction, count=remaining
                )
            moved = visual
        return moved

    def _selection_anchor_for_move(
        self, caret: MultiCursorCaret, *, select: bool
    ) -> int | None:
        """Resolve the selection anchor for a caret movement"""
        if not select:
            return None
        return caret.anchor if caret.anchor is not None else caret.position

    def _apply_navigation_carets(self, carets: list[MultiCursorCaret]) -> None:
        """Apply cursor-only movement results through the shared caret model"""
        if not carets:
            return
        if len(carets) == 1 and carets[0].is_primary:
            primary = carets[0]
            self._multi_carets = []
            self.buffer.cursor_position = primary.position
            self.buffer.preferred_column = primary.preferred_column
            self.buffer.selection_state = None
            self._wrap_preferred_column = primary.visual_column
            if primary.has_selection:
                self.buffer.selection_state = SelectionState(
                    original_cursor_position=cast(int, primary.anchor)
                )
            self.invalidate()
            return
        self._set_multi_carets(carets)

    def _moved_caret(
        self,
        caret: MultiCursorCaret,
        position: int,
        *,
        select: bool = False,
        preferred_column: int | None = None,
        visual_column: int | None = None,
    ) -> MultiCursorCaret:
        """Build one moved caret while preserving selection intent"""
        return MultiCursorCaret(
            position=max(0, min(len(self.buffer.text), position)),
            anchor=self._selection_anchor_for_move(caret, select=select),
            preferred_column=preferred_column,
            visual_column=visual_column,
            is_primary=caret.is_primary,
        )

    def move_cursors_vertical(
        self, direction: int, *, count: int = 1, select: bool = False
    ) -> None:
        """Move all active carets vertically with sticky column memory"""
        self.reattach_scroll_to_cursor()
        self.note_user_activity()
        moved: list[MultiCursorCaret] = []
        for caret in self._get_multi_carets():
            target = self._move_vertical_caret(caret, direction, count=count)
            moved.append(
                self._moved_caret(
                    caret,
                    target.position,
                    select=select,
                    preferred_column=target.preferred_column,
                    visual_column=target.visual_column,
                )
            )
        self._apply_navigation_carets(moved)

    def _move_horizontal_caret(
        self, caret: MultiCursorCaret, direction: int, *, select: bool = False
    ) -> MultiCursorCaret:
        """Move one caret left or right and clear sticky vertical memory"""
        return self._moved_caret(caret, caret.position + direction, select=select)

    def move_cursors_horizontal(self, direction: int, *, select: bool = False) -> None:
        """Move every active caret left or right"""
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        self.note_user_activity()
        self._apply_navigation_carets(
            [
                self._move_horizontal_caret(caret, direction, select=select)
                for caret in self._get_multi_carets()
            ]
        )

    def _line_start_position_for_caret(self, caret: MultiCursorCaret) -> int:
        """Return the smart line-start position for one caret"""
        document = Document(self.buffer.text, cursor_position=caret.position)
        logical_start = caret.position + document.get_start_of_line_position(
            after_whitespace=False
        )
        smart_start = caret.position + document.get_start_of_line_position(
            after_whitespace=True
        )
        if smart_start == caret.position and smart_start != logical_start:
            return logical_start
        if smart_start != logical_start and caret.position > smart_start:
            return smart_start

        render_info = self.main_window.render_info
        if (
            render_info is not None
            and self.word_wrap_enabled
            and getattr(render_info, "wrap_lines", False)
        ):
            targets = get_visual_line_targets(
                self.buffer.text,
                caret.position,
                render_info,
            )
            if targets is not None and targets.wrapped:
                if caret.position != targets.visual_start:
                    if (
                        targets.visual_start == targets.logical_start
                        and targets.logical_smart_start > targets.logical_start
                        and caret.position > targets.logical_smart_start
                    ):
                        return targets.logical_smart_start
                    return targets.visual_start
                if targets.visual_start != targets.logical_start:
                    return (
                        targets.logical_smart_start
                        if targets.logical_smart_start != targets.logical_start
                        else targets.logical_start
                    )
                if targets.logical_smart_start != targets.logical_start:
                    return (
                        targets.logical_start
                        if caret.position == targets.logical_smart_start
                        else targets.logical_smart_start
                    )
                return targets.logical_start

        if smart_start != logical_start:
            return logical_start if caret.position == smart_start else smart_start
        return logical_start

    def _line_end_position_for_caret(self, caret: MultiCursorCaret) -> int:
        """Return the logical line-end position for one caret"""
        render_info = self.main_window.render_info
        if (
            render_info is not None
            and self.word_wrap_enabled
            and getattr(render_info, "wrap_lines", False)
        ):
            targets = get_visual_line_targets(
                self.buffer.text,
                caret.position,
                render_info,
            )
            if targets is not None and targets.wrapped:
                if caret.position != targets.visual_end:
                    return targets.visual_end
                if targets.visual_end != targets.logical_end:
                    return targets.logical_end
                return targets.logical_end
        document = Document(self.buffer.text, cursor_position=caret.position)
        return caret.position + document.get_end_of_line_position()

    def move_cursors_to_line_start(self, *, select: bool = False) -> bool:
        """Move every active caret to its own smart line start"""
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        self.note_user_activity()
        self._apply_navigation_carets(
            [
                self._moved_caret(
                    caret, self._line_start_position_for_caret(caret), select=select
                )
                for caret in self._get_multi_carets()
            ]
        )
        return True

    def move_cursors_to_line_end(self, *, select: bool = False) -> bool:
        """Move every active caret to its own line end"""
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        self.note_user_activity()
        self._apply_navigation_carets(
            [
                self._moved_caret(
                    caret, self._line_end_position_for_caret(caret), select=select
                )
                for caret in self._get_multi_carets()
            ]
        )
        return True

    def move_cursors_to_document_start(self, *, select: bool = False) -> bool:
        """Move every active caret to the start of the buffer"""
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        self.note_user_activity()
        self._apply_navigation_carets(
            [
                self._moved_caret(caret, 0, select=select)
                for caret in self._get_multi_carets()
            ]
        )
        return True

    def move_cursors_to_document_end(self, *, select: bool = False) -> bool:
        """Move every active caret to the end of the buffer"""
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        self.note_user_activity()
        text_end = len(self.buffer.text)
        self._apply_navigation_carets(
            [
                self._moved_caret(caret, text_end, select=select)
                for caret in self._get_multi_carets()
            ]
        )
        return True

    def _word_move_position(self, caret: MultiCursorCaret, direction: int) -> int:
        """Resolve the previous or next word boundary for one caret"""
        document = Document(self.buffer.text, cursor_position=caret.position)
        if direction < 0:
            offset = document.find_previous_word_beginning()
            return caret.position + (offset if offset is not None else -caret.position)
        offset = document.find_next_word_beginning()
        if offset is not None:
            return caret.position + offset
        return len(self.buffer.text)

    def move_cursors_by_word(self, direction: int, *, select: bool = False) -> bool:
        """Move every active caret to the previous or next word boundary"""
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        self.note_user_activity()
        self._apply_navigation_carets(
            [
                self._moved_caret(
                    caret,
                    self._word_move_position(caret, direction),
                    select=select,
                )
                for caret in self._get_multi_carets()
            ]
        )
        return True

    def _row_col_for_caret(self, caret: MultiCursorCaret) -> tuple[int, int]:
        """Return the logical row and column for one caret position"""
        return Document(
            self.buffer.text, cursor_position=caret.position
        ).translate_index_to_position(caret.position)

    def add_vertical_cursor(self, direction: int) -> bool:
        """Clone a caret above or below the current block, keeping the original fixed"""
        self.reattach_scroll_to_cursor()
        carets = list(self._get_multi_carets())
        target = (
            min(carets, key=lambda c: self._row_col_for_caret(c)[0])
            if direction < 0
            else max(carets, key=lambda c: self._row_col_for_caret(c)[0])
        )
        document = Document(self.buffer.text, cursor_position=target.position)
        preferred = (
            target.preferred_column
            if target.preferred_column is not None
            else document.cursor_position_col
        )
        row, _col = document.translate_index_to_position(target.position)
        next_row = row + direction
        if next_row < 0 or next_row >= document.line_count:
            return False
        next_position = document.translate_row_col_to_index(next_row, preferred)
        carets.append(
            MultiCursorCaret(position=next_position, preferred_column=preferred)
        )
        self._multi_cursor_last_vertical_direction = direction
        self._set_multi_carets(carets)
        return True

    def expand_or_shrink_vertical_cursors(self, direction: int) -> bool:
        """Expand the cursor block in one direction or shrink the opposite edge"""
        if not self.multi_cursor_active():
            return self.add_vertical_cursor(direction)
        carets = list(self._get_multi_carets())
        primary_row = self.buffer.document.cursor_position_row
        opposite = [
            caret
            for caret in carets
            if not caret.is_primary
            and (
                self._row_col_for_caret(caret)[0] < primary_row
                if direction > 0
                else self._row_col_for_caret(caret)[0] > primary_row
            )
        ]
        if opposite and self._multi_cursor_last_vertical_direction == -direction:
            target = (
                min(opposite, key=lambda caret: self._row_col_for_caret(caret)[0])
                if direction > 0
                else max(opposite, key=lambda caret: self._row_col_for_caret(caret)[0])
            )
            carets.remove(target)
            self._set_multi_carets(carets)
            if not self.multi_cursor_active():
                self._multi_cursor_last_vertical_direction = 0
            return True
        return self.add_vertical_cursor(direction)

    def _apply_text_edits(self, edits: Sequence[EditorTextEdit]) -> None:
        """Apply text edits through one shared caret-rebasing pipeline"""
        if not edits:
            return
        new_text, new_carets = apply_editor_text_edits(self.buffer.text, edits)
        if not new_carets:
            new_carets = [MultiCursorCaret(position=0, is_primary=True)]
        if not any(caret.is_primary for caret in new_carets):
            new_carets[-1].is_primary = True
        primary = next(caret for caret in new_carets if caret.is_primary)
        self.buffer.save_to_undo_stack()
        self.buffer.set_document(
            Document(new_text, cursor_position=primary.position),
            bypass_readonly=True,
        )
        self.reset_cursor_navigation_memory()
        if len(new_carets) == 1 and new_carets[0].is_primary:
            self._multi_carets = []
            self.buffer.selection_state = None
            if primary.has_selection:
                self.buffer.selection_state = SelectionState(
                    original_cursor_position=cast(int, primary.anchor)
                )
            self.buffer.preferred_column = primary.preferred_column
            self._wrap_preferred_column = primary.visual_column
            self.invalidate()
            return
        self._set_multi_carets(new_carets)

    def _pair_delete_edit_for_caret(
        self, caret: MultiCursorCaret
    ) -> EditorTextEdit | None:
        """Return one paired-delete edit when the caret sits inside an auto-pair"""
        if (
            caret.has_selection
            or caret.position <= 0
            or caret.position >= len(self.buffer.text)
        ):
            return None
        opening_text = self.buffer.text[caret.position - 1 : caret.position]
        rule = get_editor_wrap_rule(self.buffer.text, caret.position, opening_text)
        if rule is None or not rule.delete_pair:
            return None
        suffix_end = caret.position + len(rule.suffix)
        if self.buffer.text[caret.position : suffix_end] != rule.suffix:
            return None
        return EditorTextEdit(
            start=caret.position - len(rule.prefix),
            end=suffix_end,
            replacement="",
            carets=(
                self._caret_target(
                    caret,
                    source_position=caret.position - len(rule.prefix),
                    anchor_source_position=None,
                ),
            ),
        )

    def replace_text_at_cursors(self, text: str) -> bool:
        """Insert text at every caret, replacing any active selection ranges"""
        carets = self._get_multi_carets()
        if not any(
            caret.is_primary is False or caret.has_selection for caret in carets
        ):
            return False
        replacements = [
            EditorTextEdit(
                start=caret.selection_start,
                end=caret.selection_end,
                replacement=text,
                carets=(
                    self._caret_target(
                        caret,
                        replacement_offset=len(text),
                        anchor_source_position=None,
                    ),
                ),
            )
            for caret in carets
        ]
        self._apply_text_edits(replacements)
        self.start_bulk_edit(text)
        return True

    def type_text_in_main_buffer(self, text: str) -> bool:
        """Type one printable payload through the shared editor edit pipeline"""
        if not text:
            return False
        carets = self._get_edit_carets()

        replacements: list[EditorTextEdit] = []
        edit_indexes: dict[tuple[int, int, str], int] = {}
        special_handled = False
        for caret in carets:
            if caret.has_selection:
                wrap_rule = get_editor_wrap_rule(self.buffer.text, caret.position, text)
                if wrap_rule is not None and wrap_rule.wrap_selection:
                    prefix = wrap_rule.prefix
                    suffix = wrap_rule.suffix
                    start = caret.selection_start
                    end = caret.selection_end
                    replacement = prefix + self.buffer.text[start:end] + suffix
                    self._merge_text_edit(
                        replacements,
                        edit_indexes,
                        start=start,
                        end=end,
                        replacement=replacement,
                        carets=(
                            self._caret_target(
                                caret,
                                replacement_offset=len(prefix)
                                + (caret.position - start),
                                anchor_replacement_offset=(
                                    0
                                    if caret.anchor is None
                                    else len(prefix) + (caret.anchor - start)
                                ),
                            ),
                        ),
                    )
                    special_handled = True
                    continue
            else:
                closing_rule = get_editor_closing_wrap_rule(
                    self.buffer.text, caret.position, text
                )
                if (
                    closing_rule is not None
                    and closing_rule.skip_over
                    and self.buffer.text.startswith(closing_rule.suffix, caret.position)
                ):
                    self._merge_text_edit(
                        replacements,
                        edit_indexes,
                        start=caret.position,
                        end=caret.position + len(closing_rule.suffix),
                        replacement=closing_rule.suffix,
                        carets=(
                            self._caret_target(
                                caret,
                                replacement_offset=len(closing_rule.suffix),
                                anchor_source_position=None,
                            ),
                        ),
                    )
                    special_handled = True
                    continue
                wrap_rule = get_editor_wrap_rule(self.buffer.text, caret.position, text)
                if wrap_rule is not None and wrap_rule.auto_pair:
                    self._merge_text_edit(
                        replacements,
                        edit_indexes,
                        start=caret.position,
                        end=caret.position,
                        replacement=wrap_rule.prefix + wrap_rule.suffix,
                        carets=(
                            self._caret_target(
                                caret,
                                replacement_offset=len(wrap_rule.prefix),
                                anchor_source_position=None,
                            ),
                        ),
                    )
                    special_handled = True
                    continue
            self._merge_text_edit(
                replacements,
                edit_indexes,
                start=caret.selection_start,
                end=caret.selection_end,
                replacement=text,
                carets=(
                    self._caret_target(
                        caret,
                        replacement_offset=len(text),
                        anchor_source_position=None,
                    ),
                ),
            )

        if (
            not self._multi_carets
            and not any(caret.has_selection for caret in carets)
            and not special_handled
        ):
            return False

        self._apply_text_edits(replacements)
        self.start_bulk_edit(text)
        return True

    def clone_current_lines_or_selections(self, *, insert_above: bool) -> bool:
        """Clone each current line or active selection while keeping originals active"""
        carets = self._get_edit_carets()
        if not carets:
            return False

        replacements: list[EditorTextEdit] = []
        edit_indexes: dict[tuple[int, int, str], int] = {}
        for caret in carets:
            if caret.has_selection:
                selection_start = caret.selection_start
                selection_end = caret.selection_end
                selection_text = self.buffer.text[selection_start:selection_end]
                linewise_selection = (
                    selection_start == 0
                    or self.buffer.text[selection_start - 1] == "\n"
                ) and (
                    selection_end == len(self.buffer.text)
                    or self.buffer.text[selection_end] == "\n"
                )
                if linewise_selection:
                    if insert_above:
                        insert_at = selection_start
                        replacement = selection_text + "\n"
                    elif selection_end < len(self.buffer.text):
                        insert_at = selection_end + 1
                        replacement = selection_text + "\n"
                    else:
                        insert_at = selection_end
                        replacement = "\n" + selection_text
                else:
                    insert_at = selection_start if insert_above else selection_end
                    replacement = selection_text
            else:
                line = get_logical_line_span(self.buffer.text, caret.position)
                insert_at, replacement = line.clone_insertion(insert_above=insert_above)

            boundary_offset = len(replacement) if insert_above else 0
            self._merge_text_edit(
                replacements,
                edit_indexes,
                start=insert_at,
                end=insert_at,
                replacement=replacement,
                carets=(
                    self._caret_target(
                        caret,
                        replacement_offset=(
                            boundary_offset if caret.position == insert_at else 0
                        ),
                        anchor_replacement_offset=(
                            boundary_offset if caret.anchor == insert_at else 0
                        ),
                    ),
                ),
            )

        self._apply_text_edits(replacements)
        return True

    def _selected_texts_at_cursors(self) -> tuple[str, ...]:
        """Return selected text fragments from active virtual carets"""
        if not self.multi_cursor_active():
            return tuple()
        selected: list[str] = []
        for caret in sorted(
            self._get_multi_carets(), key=lambda item: item.selection_start
        ):
            if caret.has_selection:
                selected.append(
                    self.buffer.text[caret.selection_start : caret.selection_end]
                )
        return tuple(selected)

    def copy_selected_text_at_cursors(self) -> str | None:
        """Copy virtual multi-cursor selections as line-separated fragments"""
        selected = self._selected_texts_at_cursors()
        if not selected:
            return None
        return "\n".join(selected)

    def cut_selected_text_at_cursors(self) -> str | None:
        """Cut all virtual multi-cursor selections without scattering carets"""
        copied = self.copy_selected_text_at_cursors()
        if copied is None:
            return None
        replacements = [
            EditorTextEdit(
                start=caret.selection_start,
                end=caret.selection_end,
                replacement="",
                carets=(self._caret_target(caret, anchor_source_position=None),),
            )
            for caret in self._get_multi_carets()
            if caret.has_selection
        ]
        self._apply_text_edits(replacements)
        return copied

    def _line_cut_edit_for_caret(self, caret: MultiCursorCaret) -> EditorTextEdit:
        """Return one line-cut edit with a VS Code-like caret target"""
        line = get_logical_line_span(self.buffer.text, caret.position)
        cut_start, cut_end = line.cut_range()
        return EditorTextEdit(
            start=cut_start,
            end=cut_end,
            replacement="",
            carets=(
                self._caret_target(
                    caret,
                    source_position=line.cut_target_position(),
                    anchor_source_position=None,
                ),
            ),
        )

    def cut_current_lines_at_cursors(self) -> str | None:
        """Cut the full logical line for each active caret"""
        carets = list(self._get_multi_carets())
        if not carets:
            return None

        deduped_edits: list[EditorTextEdit] = []
        edit_indexes: dict[tuple[int, int, str], int] = {}
        copied_parts: dict[tuple[int, int, str], str] = {}
        for caret in carets:
            line = get_logical_line_span(self.buffer.text, caret.position)
            edit = self._line_cut_edit_for_caret(caret)
            key = (edit.start, edit.end, edit.replacement)
            copied_parts.setdefault(key, line.cut_text(self.buffer.text))
            self._merge_text_edit(
                deduped_edits,
                edit_indexes,
                start=edit.start,
                end=edit.end,
                replacement=edit.replacement,
                carets=edit.carets,
            )

        copied = "".join(
            copied_parts[(edit.start, edit.end, edit.replacement)]
            for edit in deduped_edits
        )
        self._apply_text_edits(deduped_edits)
        return copied

    def delete_before_cursors(self) -> bool:
        """Delete one character before each caret, or each selected range"""
        carets = self._get_multi_carets()
        if not self.multi_cursor_active():
            pair_edit = self._pair_delete_edit_for_caret(carets[0])
            if pair_edit is None:
                return False
            self._apply_text_edits([pair_edit])
            return True
        replacements: list[EditorTextEdit] = []
        for caret in carets:
            if caret.has_selection:
                replacements.append(
                    EditorTextEdit(
                        start=caret.selection_start,
                        end=caret.selection_end,
                        replacement="",
                        carets=(
                            self._caret_target(
                                caret,
                                source_position=caret.selection_start,
                                anchor_source_position=None,
                            ),
                        ),
                    )
                )
            else:
                pair_edit = self._pair_delete_edit_for_caret(caret)
                if pair_edit is not None:
                    replacements.append(pair_edit)
                elif caret.position > 0:
                    replacements.append(
                        EditorTextEdit(
                            start=caret.position - 1,
                            end=caret.position,
                            replacement="",
                            carets=(
                                self._caret_target(
                                    caret,
                                    source_position=caret.position - 1,
                                    anchor_source_position=None,
                                ),
                            ),
                        )
                    )
        if not replacements:
            return False
        self._apply_text_edits(replacements)
        return True

    def delete_after_cursors(self) -> bool:
        """Delete one character after each caret, or each selected range"""
        carets = self._get_multi_carets()
        if not self.multi_cursor_active():
            return False
        text_length = len(self.buffer.text)
        replacements: list[EditorTextEdit] = []
        for caret in carets:
            if caret.has_selection:
                replacements.append(
                    EditorTextEdit(
                        start=caret.selection_start,
                        end=caret.selection_end,
                        replacement="",
                        carets=(
                            self._caret_target(
                                caret,
                                source_position=caret.selection_start,
                                anchor_source_position=None,
                            ),
                        ),
                    )
                )
            elif caret.position < text_length:
                replacements.append(
                    EditorTextEdit(
                        start=caret.position,
                        end=caret.position + 1,
                        replacement="",
                        carets=(
                            self._caret_target(
                                caret,
                                source_position=caret.position,
                                anchor_source_position=None,
                            ),
                        ),
                    )
                )
        if not replacements:
            return False
        self._apply_text_edits(replacements)
        return True

    def delete_word_before_cursors(self) -> bool:
        """Delete the previous word at every active virtual caret"""
        if not self.multi_cursor_active():
            return False
        replacements: list[EditorTextEdit] = []
        for caret in self._get_multi_carets():
            if caret.has_selection:
                replacements.append(
                    EditorTextEdit(
                        start=caret.selection_start,
                        end=caret.selection_end,
                        replacement="",
                        carets=(
                            self._caret_target(
                                caret,
                                source_position=caret.selection_start,
                                anchor_source_position=None,
                            ),
                        ),
                    )
                )
                continue
            if caret.position <= 0:
                continue
            document = Document(self.buffer.text, cursor_position=caret.position)
            offset = document.find_previous_word_beginning()
            start = caret.position + offset if offset is not None else 0
            if start != caret.position:
                replacements.append(
                    EditorTextEdit(
                        start=start,
                        end=caret.position,
                        replacement="",
                        carets=(
                            self._caret_target(
                                caret,
                                source_position=start,
                                anchor_source_position=None,
                            ),
                        ),
                    )
                )
        if not replacements:
            return False
        self._apply_text_edits(replacements)
        return True

    def delete_word_after_cursors(self) -> bool:
        """Delete the next word at every active virtual caret"""
        if not self.multi_cursor_active():
            return False
        replacements: list[EditorTextEdit] = []
        text_length = len(self.buffer.text)
        for caret in self._get_multi_carets():
            if caret.has_selection:
                replacements.append(
                    EditorTextEdit(
                        start=caret.selection_start,
                        end=caret.selection_end,
                        replacement="",
                        carets=(
                            self._caret_target(
                                caret,
                                source_position=caret.selection_start,
                                anchor_source_position=None,
                            ),
                        ),
                    )
                )
                continue
            if caret.position >= text_length:
                continue
            document = Document(self.buffer.text, cursor_position=caret.position)
            offset = document.find_next_word_beginning()
            end = caret.position + offset if offset is not None else text_length
            if end != caret.position:
                replacements.append(
                    EditorTextEdit(
                        start=caret.position,
                        end=end,
                        replacement="",
                        carets=(
                            self._caret_target(
                                caret,
                                source_position=caret.position,
                                anchor_source_position=None,
                            ),
                        ),
                    )
                )
        if not replacements:
            return False
        self._apply_text_edits(replacements)
        return True

    def paste_text_at_cursors(self, text: str) -> bool:
        """Paste the same payload at every active caret"""
        return self.replace_text_at_cursors(text)

    def get_multi_cursor_render_carets(self) -> tuple[MultiCursorCaret, ...]:
        """Expose the active carets to the rendering processors"""
        return tuple(
            caret for caret in self._get_multi_carets() if self.multi_cursor_active()
        )

    def scroll_view(self, direction: int, *, count: int = 1) -> None:
        """Scroll the editor viewport without moving the real cursor"""
        render_info = self.main_window.render_info
        if render_info is None:
            return
        max_scroll = max(0, render_info.content_height - render_info.window_height)
        current_scroll = (
            self._detached_vertical_scroll
            if self._detached_vertical_scroll is not None
            else self.main_window.vertical_scroll
        )
        self._detached_vertical_scroll = max(
            0, min(max_scroll, current_scroll + (direction * count))
        )
        self.main_window.vertical_scroll = self._detached_vertical_scroll
        self.invalidate()

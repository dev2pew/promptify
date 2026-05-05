"""Multi-caret state and editing helpers for the interactive editor"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from ...shared.editor_state import EditorTextEdit, MultiCursorCaret, SearchOptions
from ...shared.editor_support import apply_editor_text_edits
from ._imports import Buffer, Document, Window


class EditorMultiCursorMixin:
    """Provide VS Code-style sticky-column and multi-cursor editing behavior"""

    _multi_carets: list[MultiCursorCaret] = []
    _multi_cursor_owned_search: bool = False
    _multi_cursor_occurrence_query: str = ""
    _multi_cursor_last_vertical_direction: int = 0
    _wrap_preferred_column: int | None = None
    _detached_vertical_scroll: int | None = None
    _internal_clipboard_text: str = ""
    buffer: Buffer = cast(Buffer, cast(object, None))
    search_buffer: Buffer = cast(Buffer, cast(object, None))
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
            is_primary=True,
        )

    def _get_multi_carets(self) -> tuple[MultiCursorCaret, ...]:
        """Return the active virtual carets or a single live primary caret"""
        if self._multi_carets:
            return tuple(self._multi_carets)
        return (self._make_primary_caret(),)

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
        return MultiCursorCaret(
            position=end,
            anchor=start if start != end else None,
            preferred_column=preferred_column,
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
        """Show the search widget as an indicator for occurrence-based carets"""
        self.search_visible = True
        self.replace_visible = False
        self._multi_cursor_owned_search = True
        self.search_buffer.document = Document(query, cursor_position=len(query))

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

        document = Document(self.buffer.text, cursor_position=caret.position)
        row, col = document.translate_index_to_position(caret.position)
        visible_items = sorted(render_info.visible_line_to_row_col.items())
        if not visible_items:
            return None

        current_index: int | None = None
        current_start_col = 0
        for index, (_visible_row, (item_row, start_col)) in enumerate(visible_items):
            if item_row != row:
                continue
            next_col = len(document.lines[row])
            if index + 1 < len(visible_items) and visible_items[index + 1][1][0] == row:
                next_col = visible_items[index + 1][1][1]
            if col < next_col or index == len(visible_items) - 1:
                current_index = index
                current_start_col = start_col
                break
        else:
            return None

        target_index = current_index + direction
        if target_index < 0 or target_index >= len(visible_items):
            return None

        preferred = (
            self._wrap_preferred_column
            if caret.is_primary and not self.multi_cursor_active()
            else caret.preferred_column
        )
        if preferred is None:
            preferred = max(0, col - current_start_col)

        target_row, target_start_col = visible_items[target_index][1]
        target_end_col = len(document.lines[target_row])
        if (
            target_index + 1 < len(visible_items)
            and visible_items[target_index + 1][1][0] == target_row
        ):
            target_end_col = visible_items[target_index + 1][1][1]
        target_col = min(target_start_col + preferred, target_end_col)
        target_position = document.translate_row_col_to_index(target_row, target_col)

        if caret.is_primary and not self.multi_cursor_active():
            self._wrap_preferred_column = preferred
        return MultiCursorCaret(
            position=target_position,
            anchor=None,
            preferred_column=preferred,
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

    def _moved_caret(
        self,
        caret: MultiCursorCaret,
        position: int,
        *,
        select: bool = False,
        preferred_column: int | None = None,
    ) -> MultiCursorCaret:
        """Build one moved caret while preserving selection intent"""
        return MultiCursorCaret(
            position=max(0, min(len(self.buffer.text), position)),
            anchor=self._selection_anchor_for_move(caret, select=select),
            preferred_column=preferred_column,
            is_primary=caret.is_primary,
        )

    def move_cursors_vertical(
        self, direction: int, *, count: int = 1, select: bool = False
    ) -> None:
        """Move all active carets vertically with sticky column memory"""
        self.reattach_scroll_to_cursor()
        if not self.multi_cursor_active():
            moved = self._move_vertical_caret(
                self._make_primary_caret(), direction, count=count
            )
            self.buffer.cursor_position = moved.position
            self.buffer.preferred_column = moved.preferred_column
            return
        self.note_user_activity()
        moved = []
        for caret in self._get_multi_carets():
            target = self._move_vertical_caret(caret, direction, count=count)
            moved.append(
                self._moved_caret(
                    caret,
                    target.position,
                    select=select,
                    preferred_column=target.preferred_column,
                )
            )
        self._set_multi_carets(moved)

    def _move_horizontal_caret(
        self, caret: MultiCursorCaret, direction: int, *, select: bool = False
    ) -> MultiCursorCaret:
        """Move one caret left or right and clear sticky vertical memory"""
        return self._moved_caret(caret, caret.position + direction, select=select)

    def move_cursors_horizontal(self, direction: int, *, select: bool = False) -> None:
        """Move every active caret left or right"""
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        if not self.multi_cursor_active():
            if direction < 0 and self.buffer.cursor_position > 0:
                self.buffer.cursor_position -= 1
            elif direction > 0 and self.buffer.cursor_position < len(self.buffer.text):
                self.buffer.cursor_position += 1
            self.buffer.preferred_column = None
            return
        self.note_user_activity()
        self._set_multi_carets(
            [
                self._move_horizontal_caret(caret, direction, select=select)
                for caret in self._get_multi_carets()
            ]
        )

    def _line_start_position_for_caret(self, caret: MultiCursorCaret) -> int:
        """Return the smart line-start position for one caret"""
        document = Document(self.buffer.text, cursor_position=caret.position)
        first_non_ws = document.get_start_of_line_position(after_whitespace=True)
        if first_non_ws == 0:
            first_non_ws = document.get_start_of_line_position(after_whitespace=False)
        return caret.position + first_non_ws

    def _line_end_position_for_caret(self, caret: MultiCursorCaret) -> int:
        """Return the logical line-end position for one caret"""
        document = Document(self.buffer.text, cursor_position=caret.position)
        return caret.position + document.get_end_of_line_position()

    def move_cursors_to_line_start(self, *, select: bool = False) -> bool:
        """Move every active caret to its own smart line start"""
        if not self.multi_cursor_active():
            return False
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        self.note_user_activity()
        self._set_multi_carets(
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
        if not self.multi_cursor_active():
            return False
        self.reattach_scroll_to_cursor()
        self.reset_cursor_navigation_memory()
        self.note_user_activity()
        self._set_multi_carets(
            [
                self._moved_caret(
                    caret, self._line_end_position_for_caret(caret), select=select
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
        if not any(caret.is_primary for caret in new_carets):
            new_carets[-1].is_primary = True
        primary = next(caret for caret in new_carets if caret.is_primary)
        self.buffer.save_to_undo_stack()
        self.buffer.set_document(
            Document(new_text, cursor_position=primary.position),
            bypass_readonly=True,
        )
        self.reset_cursor_navigation_memory()
        self._set_multi_carets(new_carets)

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
                caret_source_position=caret.selection_end,
                caret_replacement_offset=len(text),
                is_primary=caret.is_primary,
            )
            for caret in carets
        ]
        self._apply_text_edits(replacements)
        self.start_bulk_edit(text)
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
                caret_source_position=caret.selection_start,
                is_primary=caret.is_primary,
            )
            for caret in self._get_multi_carets()
            if caret.has_selection
        ]
        self._apply_text_edits(replacements)
        return copied

    def _line_cut_edit_for_position(
        self, position: int, *, is_primary: bool
    ) -> EditorTextEdit:
        """Return one line-cut edit with a VS Code-like caret target"""
        document = Document(self.buffer.text, cursor_position=position)
        row = document.cursor_position_row
        line = document.current_line
        line_start = document.translate_row_col_to_index(row, 0)
        line_end = document.translate_row_col_to_index(row, len(line))
        if row > 0:
            target_position = document.translate_row_col_to_index(row - 1, 0)
        else:
            target_position = line_start
        if row < document.line_count - 1:
            return EditorTextEdit(
                start=line_start,
                end=line_end + 1,
                replacement="",
                caret_source_position=target_position,
                is_primary=is_primary,
            )
        if row > 0:
            return EditorTextEdit(
                start=line_start - 1,
                end=line_end,
                replacement="",
                caret_source_position=target_position,
                is_primary=is_primary,
            )
        return EditorTextEdit(
            start=line_start,
            end=line_end,
            replacement="",
            caret_source_position=target_position,
            is_primary=is_primary,
        )

    def cut_current_lines_at_cursors(self) -> str | None:
        """Cut the full logical line for each active caret"""
        carets = list(self._get_multi_carets())
        if not carets:
            return None

        ordered_edits = [
            self._line_cut_edit_for_position(
                caret.position, is_primary=caret.is_primary
            )
            for caret in carets
        ]
        ordered_edits.sort(key=lambda item: (item.start, item.end))
        deduped_edits: list[EditorTextEdit] = []
        for edit in ordered_edits:
            if (
                deduped_edits
                and deduped_edits[-1].start == edit.start
                and deduped_edits[-1].end == edit.end
            ):
                previous = deduped_edits[-1]
                deduped_edits[-1] = EditorTextEdit(
                    start=previous.start,
                    end=previous.end,
                    replacement=previous.replacement,
                    caret_source_position=previous.caret_source_position,
                    caret_replacement_offset=previous.caret_replacement_offset,
                    is_primary=previous.is_primary or edit.is_primary,
                )
                continue
            deduped_edits.append(edit)

        copied = "".join(
            self.buffer.text[edit.start : edit.end].lstrip("\n")
            for edit in deduped_edits
        )
        self._apply_text_edits(deduped_edits)
        return copied

    def delete_before_cursors(self) -> bool:
        """Delete one character before each caret, or each selected range"""
        carets = self._get_multi_carets()
        if not self.multi_cursor_active():
            return False
        replacements: list[EditorTextEdit] = []
        for caret in carets:
            if caret.has_selection:
                replacements.append(
                    EditorTextEdit(
                        start=caret.selection_start,
                        end=caret.selection_end,
                        replacement="",
                        caret_source_position=caret.selection_start,
                        is_primary=caret.is_primary,
                    )
                )
            elif caret.position > 0:
                replacements.append(
                    EditorTextEdit(
                        start=caret.position - 1,
                        end=caret.position,
                        replacement="",
                        caret_source_position=caret.position - 1,
                        is_primary=caret.is_primary,
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
                        caret_source_position=caret.selection_start,
                        is_primary=caret.is_primary,
                    )
                )
            elif caret.position < text_length:
                replacements.append(
                    EditorTextEdit(
                        start=caret.position,
                        end=caret.position + 1,
                        replacement="",
                        caret_source_position=caret.position,
                        is_primary=caret.is_primary,
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
                        caret_source_position=caret.selection_start,
                        is_primary=caret.is_primary,
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
                        caret_source_position=start,
                        is_primary=caret.is_primary,
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
                        caret_source_position=caret.selection_start,
                        is_primary=caret.is_primary,
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
                        caret_source_position=caret.position,
                        is_primary=caret.is_primary,
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

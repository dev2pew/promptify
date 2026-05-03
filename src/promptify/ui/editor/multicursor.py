"""Multi-caret state and editing helpers for the interactive editor"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from ...shared.editor_state import MultiCursorCaret, SearchOptions
from ._imports import Buffer, Document, Window


class EditorMultiCursorMixin:
    """Provide VS Code-style sticky-column and multi-cursor editing behavior"""

    _multi_carets: list[MultiCursorCaret] = []
    _multi_cursor_owned_search: bool = False
    _multi_cursor_occurrence_query: str = ""
    _multi_cursor_last_vertical_direction: int = 0
    buffer: Buffer = cast(Buffer, cast(object, None))
    search_buffer: Buffer = cast(Buffer, cast(object, None))
    main_window: Window = cast(Window, cast(object, None))
    search_visible: bool = False
    replace_visible: bool = False
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

    def multi_cursor_active(self) -> bool:
        """Return whether extra virtual carets or selections are active"""
        return any(
            caret.is_primary is False or caret.has_selection
            for caret in self._get_multi_carets()
        )

    def _merge_multi_carets(
        self, carets: list[MultiCursorCaret]
    ) -> list[MultiCursorCaret]:
        """Merge colliding carets while preserving the primary cursor"""
        merged: dict[tuple[int, int], MultiCursorCaret] = {}
        for caret in carets:
            key = caret.range_key
            current = merged.get(key)
            if current is None or caret.is_primary:
                merged[key] = caret
        ordered = sorted(
            merged.values(),
            key=lambda caret: (
                caret.selection_start,
                caret.selection_end,
                caret.position,
            ),
        )
        if not any(caret.is_primary for caret in ordered):
            ordered.append(self._make_primary_caret())
        return ordered

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
        if self._multi_cursor_owned_search:
            self.search_visible = False
            self.replace_visible = False
            self._multi_cursor_owned_search = False
            self._focus_main()
        self.buffer.selection_state = None
        self.buffer.preferred_column = None
        self.invalidate()

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

    def _move_vertical_caret(
        self, caret: MultiCursorCaret, direction: int, *, count: int = 1
    ) -> MultiCursorCaret:
        """Move one caret up or down while keeping its preferred column sticky"""
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

    def move_cursors_vertical(self, direction: int, *, count: int = 1) -> None:
        """Move all active carets vertically with sticky column memory"""
        if not self.multi_cursor_active():
            if direction > 0:
                self.buffer.cursor_down(count=count)
            else:
                self.buffer.cursor_up(count=count)
            return
        self.note_user_activity()
        moved = [
            self._move_vertical_caret(caret, direction, count=count)
            for caret in self._get_multi_carets()
        ]
        self._set_multi_carets(moved)

    def _move_horizontal_caret(
        self, caret: MultiCursorCaret, direction: int
    ) -> MultiCursorCaret:
        """Move one caret left or right and clear sticky vertical memory"""
        position = caret.position + direction
        position = max(0, min(len(self.buffer.text), position))
        return MultiCursorCaret(
            position=position, anchor=None, is_primary=caret.is_primary
        )

    def move_cursors_horizontal(self, direction: int) -> None:
        """Move every active caret left or right"""
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
                self._move_horizontal_caret(caret, direction)
                for caret in self._get_multi_carets()
            ]
        )

    def _row_col_for_caret(self, caret: MultiCursorCaret) -> tuple[int, int]:
        """Return the logical row and column for one caret position"""
        return Document(
            self.buffer.text, cursor_position=caret.position
        ).translate_index_to_position(caret.position)

    def add_vertical_cursor(self, direction: int) -> bool:
        """Clone a caret above or below the current block, keeping the original fixed"""
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
                max(opposite, key=lambda caret: self._row_col_for_caret(caret)[0])
                if direction > 0
                else min(opposite, key=lambda caret: self._row_col_for_caret(caret)[0])
            )
            carets.remove(target)
            self._set_multi_carets(carets)
            if not self.multi_cursor_active():
                self._multi_cursor_last_vertical_direction = 0
            return True
        return self.add_vertical_cursor(direction)

    def _apply_multi_replacements(
        self,
        replacements: list[tuple[int, int, str]],
        *,
        primary_index: int = 0,
    ) -> None:
        """Apply sorted replacements and place one collapsed caret after each edit"""
        if not replacements:
            return
        new_text = self.buffer.text
        new_carets: list[MultiCursorCaret] = []
        for order, (start, end, replacement) in enumerate(
            sorted(replacements, key=lambda item: (item[0], item[1]), reverse=True)
        ):
            new_text = new_text[:start] + replacement + new_text[end:]
            new_carets.append(
                MultiCursorCaret(
                    position=start + len(replacement),
                    is_primary=order == primary_index,
                )
            )
        self.buffer.save_to_undo_stack()
        primary = next(
            (caret for caret in new_carets if caret.is_primary), new_carets[0]
        )
        if not any(caret.is_primary for caret in new_carets):
            primary.is_primary = True
        self.buffer.set_document(
            Document(new_text, cursor_position=primary.position),
            bypass_readonly=True,
        )
        self._set_multi_carets(new_carets)

    def replace_text_at_cursors(self, text: str) -> bool:
        """Insert text at every caret, replacing any active selection ranges"""
        carets = self._get_multi_carets()
        if not any(
            caret.is_primary is False or caret.has_selection for caret in carets
        ):
            return False
        replacements = [
            (caret.selection_start, caret.selection_end, text) for caret in carets
        ]
        primary_order = next(
            index
            for index, caret in enumerate(
                sorted(
                    carets,
                    key=lambda c: (c.selection_start, c.selection_end),
                    reverse=True,
                )
            )
            if caret.is_primary
        )
        self._apply_multi_replacements(replacements, primary_index=primary_order)
        self.start_bulk_edit(text)
        return True

    def delete_before_cursors(self) -> bool:
        """Delete one character before each caret, or each selected range"""
        carets = self._get_multi_carets()
        if not self.multi_cursor_active():
            return False
        replacements: list[tuple[int, int, str]] = []
        for caret in carets:
            if caret.has_selection:
                replacements.append((caret.selection_start, caret.selection_end, ""))
            elif caret.position > 0:
                replacements.append((caret.position - 1, caret.position, ""))
        if not replacements:
            return False
        primary_order = next(
            index
            for index, caret in enumerate(
                sorted(
                    carets,
                    key=lambda c: (c.selection_start, c.selection_end),
                    reverse=True,
                )
            )
            if caret.is_primary
        )
        self._apply_multi_replacements(replacements, primary_index=primary_order)
        return True

    def delete_after_cursors(self) -> bool:
        """Delete one character after each caret, or each selected range"""
        carets = self._get_multi_carets()
        if not self.multi_cursor_active():
            return False
        text_length = len(self.buffer.text)
        replacements: list[tuple[int, int, str]] = []
        for caret in carets:
            if caret.has_selection:
                replacements.append((caret.selection_start, caret.selection_end, ""))
            elif caret.position < text_length:
                replacements.append((caret.position, caret.position + 1, ""))
        if not replacements:
            return False
        primary_order = next(
            index
            for index, caret in enumerate(
                sorted(
                    carets,
                    key=lambda c: (c.selection_start, c.selection_end),
                    reverse=True,
                )
            )
            if caret.is_primary
        )
        self._apply_multi_replacements(replacements, primary_index=primary_order)
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
        self.main_window.vertical_scroll = max(
            0,
            min(max_scroll, self.main_window.vertical_scroll + (direction * count)),
        )
        self.invalidate()

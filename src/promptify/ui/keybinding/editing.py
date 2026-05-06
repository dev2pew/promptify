"""Editing, clipboard, cursor movement, and save bindings"""

from __future__ import annotations

import asyncio
import re
import time

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import has_selection
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.selection import SelectionState

from ...core.context import get_comment_syntax
from ...shared.editor_support import get_active_editor_context, get_logical_line_span
from .context import EditorBindingContext
from .sequences import (
    CTRL_ALT_DOWN,
    CTRL_ALT_UP,
    CTRL_SHIFT_ALT_DOWN,
    CTRL_SHIFT_ALT_UP,
    CTRL_SHIFT_C,
    CTRL_SHIFT_V,
    SHIFT_ALT_DOWN,
    SHIFT_ALT_UP,
)


def _get_selected_row_range(buffer: Buffer) -> tuple[int, int]:
    """Return the inclusive selected row range or the current row"""
    document = buffer.document
    if buffer.selection_state:
        start_row = document.translate_index_to_position(
            buffer.selection_state.original_cursor_position
        )[0]
        end_row = document.cursor_position_row
        if start_row > end_row:
            start_row, end_row = end_row, start_row
        return start_row, end_row
    row = document.cursor_position_row
    return row, row


def _collapse_selection(buffer: Buffer, *, to_end: bool) -> bool:
    """Collapse an active selection to one edge without moving farther"""
    if buffer.selection_state is None:
        return False
    anchor = buffer.selection_state.original_cursor_position
    cursor = buffer.cursor_position
    buffer.selection_state = None
    buffer.cursor_position = max(anchor, cursor) if to_end else min(anchor, cursor)
    buffer.preferred_column = None
    return True


def _prepare_plain_navigation(ctx: EditorBindingContext, buffer: Buffer) -> None:
    """Reset viewport and sticky-column state before plain navigation"""
    ctx.editor.reattach_scroll_to_cursor()
    ctx.editor.reset_cursor_navigation_memory()
    buffer.selection_state = None


def _cut_entire_current_line(buffer: Buffer) -> str:
    """Cut and return the current logical line, including its separator when possible"""
    line = get_logical_line_span(buffer.text, buffer.cursor_position)
    start, end = line.cut_range()
    copied_text = line.cut_text(buffer.text)

    buffer.save_to_undo_stack()
    buffer.set_document(
        Document(
            buffer.text[:start] + buffer.text[end:],
            cursor_position=line.cut_target_position(),
        ),
        bypass_readonly=True,
    )
    buffer.selection_state = None
    buffer.preferred_column = None
    return copied_text


def register_editing_bindings(ctx: EditorBindingContext) -> None:
    """Register bindings for editing, selection, cursor movement, and save"""

    editor_text_focus = ctx.editor_focus & ~ctx.is_modal_visible
    editable_text_focus = editor_text_focus | ctx.search_widget_focus | ctx.jump_focus
    editor_command_focus = editor_text_focus & ~ctx.has_completions_menu

    @ctx.bind("c-a", filter=editable_text_focus)
    def _select_all(event: KeyPressEvent) -> None:
        buffer = event.app.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.multi_cursor_active():
            ctx.editor.clear_multi_cursors()
        buffer.selection_state = SelectionState(original_cursor_position=0)
        buffer.cursor_position = len(buffer.text)

    def _get_selected_text_for_clipboard(buffer: Buffer) -> str:
        if buffer is ctx.editor.buffer:
            copied = ctx.editor.copy_selected_text_at_cursors()
            if copied is not None:
                return copied
        if buffer.selection_state:
            return buffer.copy_selection().text
        return ""

    @ctx.bind("c-c", filter=editable_text_focus)
    def _copy(event: KeyPressEvent) -> None:
        text = _get_selected_text_for_clipboard(event.app.current_buffer)
        if text:
            ctx.editor.set_internal_clipboard_text(text)
            ctx.schedule_system_clipboard_copy(text)

    @ctx.bind_sequences(CTRL_SHIFT_C, filter=editable_text_focus)
    def _copy_system_clipboard(event: KeyPressEvent) -> None:
        text = _get_selected_text_for_clipboard(event.app.current_buffer)
        if text:
            ctx.schedule_system_clipboard_copy(text)

    @ctx.bind("c-x", filter=editable_text_focus, eager=True)
    def _cut(event: KeyPressEvent) -> None:
        buffer = event.app.current_buffer
        if buffer is ctx.editor.buffer:
            cut_text = ctx.editor.cut_selected_text_at_cursors()
            if cut_text is not None:
                ctx.editor.set_internal_clipboard_text(cut_text)
                ctx.schedule_system_clipboard_copy(cut_text)
                return
            cut_text = ctx.editor.cut_current_lines_at_cursors()
            if cut_text:
                ctx.editor.set_internal_clipboard_text(cut_text)
                ctx.schedule_system_clipboard_copy(cut_text)
                return
        if buffer.selection_state:
            data = buffer.cut_selection()
            ctx.editor.set_internal_clipboard_text(data.text)
            ctx.schedule_system_clipboard_copy(data.text)
            buffer.selection_state = None
            return
        cut_text = _cut_entire_current_line(buffer)
        if cut_text:
            ctx.editor.set_internal_clipboard_text(cut_text)
            ctx.schedule_system_clipboard_copy(cut_text)

    @ctx.bind("c-v", filter=editable_text_focus)
    def _paste(event: KeyPressEvent) -> None:
        ctx.schedule_system_clipboard_paste()

    @ctx.bind_sequences(CTRL_SHIFT_V, filter=editable_text_focus)
    @ctx.bind("s-insert", filter=editable_text_focus)
    @ctx.bind("c-s-insert", filter=editable_text_focus)
    def _paste_system_clipboard(event: KeyPressEvent) -> None:
        ctx.schedule_system_clipboard_paste()

    @ctx.bind("escape", "[", "2", ";", "2", "~", filter=editable_text_focus)
    @ctx.bind("escape", "[", "2", ";", "6", "~", filter=editable_text_focus)
    def _paste_system_clipboard_xterm_insert(event: KeyPressEvent) -> None:
        ctx.schedule_system_clipboard_paste()

    @ctx.bind(Keys.BracketedPaste, filter=editable_text_focus)
    def _paste_terminal_payload(event: KeyPressEvent) -> None:
        buffer = event.app.current_buffer
        text = event.data.replace("\r\n", "\n").replace("\r", "\n")
        ctx.editor.paste_text(buffer, text)

    @ctx.bind("c-z", filter=editable_text_focus)
    def _undo(event: KeyPressEvent) -> None:
        if ctx.editor.multi_cursor_active():
            ctx.editor.clear_multi_cursors()
        event.app.current_buffer.undo()

    @ctx.bind("c-y", filter=editable_text_focus, eager=True)
    def _redo(event: KeyPressEvent) -> None:
        if ctx.editor.multi_cursor_active():
            ctx.editor.clear_multi_cursors()
        event.app.current_buffer.redo()

    @ctx.bind("home", filter=ctx.text_focus, note_activity=True)
    def _home(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=False):
            ctx.editor.reattach_scroll_to_cursor()
            return
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_to_line_start()
            return
        _prepare_plain_navigation(ctx, buffer)
        buffer.cursor_position += ctx.get_home_position(buffer.document)

    @ctx.bind("end", filter=ctx.text_focus, note_activity=True)
    def _end(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=True):
            ctx.editor.reattach_scroll_to_cursor()
            return
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_to_line_end()
            return
        _prepare_plain_navigation(ctx, buffer)
        buffer.cursor_position += buffer.document.get_end_of_line_position()

    @ctx.bind("pageup", filter=editor_text_focus)
    def _pageup(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=False):
            ctx.editor.reattach_scroll_to_cursor()
            return
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_vertical(-1, count=15)
            return
        _prepare_plain_navigation(ctx, buffer)
        buffer.cursor_up(count=15)

    @ctx.bind("pagedown", filter=editor_text_focus)
    def _pagedown(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=True):
            ctx.editor.reattach_scroll_to_cursor()
            return
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_vertical(1, count=15)
            return
        _prepare_plain_navigation(ctx, buffer)
        buffer.cursor_down(count=15)

    @ctx.bind("c-home", filter=ctx.text_focus, note_activity=True)
    def _c_home(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=False):
            ctx.editor.reattach_scroll_to_cursor()
            return
        _prepare_plain_navigation(ctx, buffer)
        buffer.cursor_position = 0

    @ctx.bind("c-end", filter=ctx.text_focus, note_activity=True)
    def _c_end(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=True):
            ctx.editor.reattach_scroll_to_cursor()
            return
        _prepare_plain_navigation(ctx, buffer)
        buffer.cursor_position = len(buffer.text)

    @ctx.bind("c-left", filter=ctx.text_focus)
    def _c_left(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=False):
            ctx.editor.reattach_scroll_to_cursor()
            return
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_by_word(-1)
            return
        _prepare_plain_navigation(ctx, buffer)
        position = buffer.document.find_previous_word_beginning()
        buffer.cursor_position += (
            position if position is not None else -buffer.cursor_position
        )

    @ctx.bind("c-right", filter=ctx.text_focus)
    def _c_right(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=True):
            ctx.editor.reattach_scroll_to_cursor()
            return
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_by_word(1)
            return
        _prepare_plain_navigation(ctx, buffer)
        position = buffer.document.find_next_word_beginning()
        if position is not None:
            buffer.cursor_position += position
        else:
            buffer.cursor_position = len(buffer.text)

    @ctx.bind("s-home", filter=editable_text_focus)
    def _s_home(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.move_cursors_to_line_start(
            select=True
        ):
            return
        ctx.start_selection(buffer)
        buffer.cursor_position += ctx.get_home_position(buffer.document)

    @ctx.bind("s-end", filter=editable_text_focus)
    def _s_end(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.move_cursors_to_line_end(
            select=True
        ):
            return
        ctx.start_selection(buffer)
        buffer.cursor_position += buffer.document.get_end_of_line_position()

    @ctx.bind("s-pageup", filter=editor_text_focus)
    def _s_pageup(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_vertical(-1, count=15, select=True)
            return
        ctx.start_selection(buffer)
        buffer.cursor_position += buffer.document.get_cursor_up_position(count=15)

    @ctx.bind("s-pagedown", filter=editor_text_focus)
    def _s_pagedown(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_vertical(1, count=15, select=True)
            return
        ctx.start_selection(buffer)
        buffer.cursor_position += buffer.document.get_cursor_down_position(count=15)

    @ctx.bind("s-c-home", filter=editable_text_focus)
    def _s_c_home(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.multi_cursor_active():
            ctx.editor.clear_multi_cursors()
        ctx.start_selection(buffer)
        buffer.cursor_position = 0

    @ctx.bind("s-c-end", filter=editable_text_focus)
    def _s_c_end(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.multi_cursor_active():
            ctx.editor.clear_multi_cursors()
        ctx.start_selection(buffer)
        buffer.cursor_position = len(buffer.text)

    @ctx.bind("s-c-left", filter=editable_text_focus)
    def _s_c_left(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_by_word(-1, select=True)
            return
        ctx.start_selection(buffer)
        position = buffer.document.find_previous_word_beginning()
        buffer.cursor_position += (
            position if position is not None else -buffer.cursor_position
        )

    @ctx.bind("s-c-right", filter=editable_text_focus)
    def _s_c_right(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_by_word(1, select=True)
            return
        ctx.start_selection(buffer)
        position = buffer.document.find_next_word_beginning()
        if position is not None:
            buffer.cursor_position += position
        else:
            buffer.cursor_position = len(buffer.text)

    @ctx.bind("c-w", filter=editable_text_focus)
    def _delete_previous_word(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.delete_word_before_cursors():
            return
        if buffer.selection_state:
            buffer.cut_selection()
            buffer.selection_state = None
            return

        position = buffer.document.find_previous_word_beginning()
        if position is not None:
            buffer.delete_before_cursor(count=-position)
        else:
            buffer.delete_before_cursor(count=buffer.cursor_position)

    @ctx.bind("c-delete", filter=editable_text_focus)
    def _delete_next_word(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.delete_word_after_cursors():
            return
        if buffer.selection_state:
            buffer.cut_selection()
            buffer.selection_state = None
            return

        position = buffer.document.find_next_word_beginning()
        if position is not None:
            buffer.delete(count=position)
        else:
            buffer.delete(count=len(buffer.text) - buffer.cursor_position)

    @ctx.bind("backspace", filter=editable_text_focus & has_selection, eager=True)
    @ctx.bind("delete", filter=editable_text_focus & has_selection, eager=True)
    def _delete_selection(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.delete_before_cursors():
            return
        buffer.cut_selection()
        buffer.selection_state = None

    @ctx.bind("backspace", filter=editor_text_focus)
    def _delete_before_cursor(event: KeyPressEvent) -> None:
        if ctx.editor.delete_before_cursors():
            return
        event.current_buffer.delete_before_cursor()

    @ctx.bind("delete", filter=editor_text_focus)
    def _delete_after_cursor(event: KeyPressEvent) -> None:
        if ctx.editor.delete_after_cursors():
            return
        event.current_buffer.delete()

    @ctx.bind(
        "<any>", filter=(editable_text_focus & has_selection) & ~editor_text_focus
    )
    def _type_over_selection(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if event.data and event.data.isprintable():
            if buffer is ctx.editor.buffer and ctx.editor.type_text_in_main_buffer(
                event.data
            ):
                return
            buffer.cut_selection()
            buffer.selection_state = None
            buffer.insert_text(event.data)
        else:
            buffer.selection_state = None

    @ctx.bind(
        "<any>",
        filter=editor_text_focus,
    )
    def _type_in_main_editor(event: KeyPressEvent) -> None:
        if not event.data or not event.data.isprintable():
            return
        if ctx.editor.type_text_in_main_buffer(event.data):
            return
        event.current_buffer.insert_text(event.data)

    # Track entry time to distinguish simulated terminal paste logic from real typing.
    last_enter_time = [0.0]

    @ctx.bind("enter", filter=editor_command_focus)
    def _smart_enter(event: KeyPressEvent) -> None:
        now = time.time()
        is_paste = (now - last_enter_time[0]) < 0.05
        last_enter_time[0] = now

        buffer = event.current_buffer
        if ctx.editor.multi_cursor_active():
            document = buffer.document
            current_line = document.current_line
            indent_str = ctx.detect_indent_style(document)
            indent_match = re.match(r"^(\s*)", current_line)
            indent = indent_match.group(1) if indent_match else ""
            if current_line.rstrip().endswith((":")) or current_line.rstrip().endswith(
                ("{", "[", "(")
            ):
                indent += indent_str
            ctx.editor.replace_text_at_cursors("\n" + indent)
            return
        if buffer.selection_state:
            buffer.cut_selection()
            buffer.selection_state = None

        if is_paste:
            buffer.insert_text("\n")
            return

        document = buffer.document
        indent_str = ctx.detect_indent_style(document)
        current_line = document.current_line
        indent_match = re.match(r"^(\s*)", current_line)
        indent = indent_match.group(1) if indent_match else ""
        if current_line.rstrip().endswith((":")) or current_line.rstrip().endswith(
            ("{", "[", "(")
        ):
            indent += indent_str
        buffer.insert_text("\n" + indent)

    @ctx.bind("tab", filter=editor_command_focus)
    def _tab(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        document = buffer.document
        indent_str = ctx.detect_indent_style(document)
        if ctx.editor.multi_cursor_active():
            ctx.editor.replace_text_at_cursors(indent_str)
            return

        if buffer.selection_state:
            start_row, end_row = _get_selected_row_range(buffer)
            lines = document.lines[:]
            for index in range(start_row, end_row + 1):
                lines[index] = indent_str + lines[index]

            cursor_row = document.cursor_position_row
            cursor_col = document.cursor_position_col + len(indent_str)
            buffer.text = "\n".join(lines)
            buffer.cursor_position = buffer.document.translate_row_col_to_index(
                cursor_row,
                cursor_col,
            )
            return

        buffer.insert_text(indent_str)

    @ctx.bind("s-tab", filter=editor_command_focus)
    def _s_tab(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        document = buffer.document
        indent_str = ctx.detect_indent_style(document)
        indent_len = len(indent_str)
        start_row, end_row = _get_selected_row_range(buffer)
        lines = document.lines[:]
        cursor_col_offset = 0

        for index in range(start_row, end_row + 1):
            line = lines[index]
            if line.startswith(indent_str):
                lines[index] = line[indent_len:]
                if index == end_row:
                    cursor_col_offset = -indent_len
            elif line.startswith("\t"):
                lines[index] = line[1:]
                if index == end_row:
                    cursor_col_offset = -1
            elif line.startswith(" "):
                spaces = len(line) - len(line.lstrip(" "))
                to_remove = min(spaces, indent_len)
                lines[index] = line[to_remove:]
                if index == end_row:
                    cursor_col_offset = -to_remove

        cursor_row = document.cursor_position_row
        cursor_col = max(0, document.cursor_position_col + cursor_col_offset)
        buffer.text = "\n".join(lines)
        buffer.cursor_position = buffer.document.translate_row_col_to_index(
            cursor_row,
            cursor_col,
        )

    @ctx.bind(
        "left", filter=ctx.text_focus & ~ctx.has_completions_menu, note_activity=True
    )
    def _left(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=False):
            ctx.editor.reattach_scroll_to_cursor()
            return
        _prepare_plain_navigation(ctx, buffer)
        if ctx.editor.multi_cursor_active():
            ctx.editor.move_cursors_horizontal(-1)
            return
        if buffer.cursor_position > 0:
            buffer.cursor_position -= 1
        buffer.preferred_column = None

    @ctx.bind(
        "right",
        filter=ctx.text_focus & ~ctx.has_completions_menu,
        note_activity=True,
    )
    def _right(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=True):
            ctx.editor.reattach_scroll_to_cursor()
            return
        _prepare_plain_navigation(ctx, buffer)
        if ctx.editor.multi_cursor_active():
            ctx.editor.move_cursors_horizontal(1)
            return
        if buffer.cursor_position < len(buffer.text):
            buffer.cursor_position += 1
        buffer.preferred_column = None

    @ctx.bind("s-left", filter=editable_text_focus & ~ctx.has_completions_menu)
    def _s_left(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.multi_cursor_active():
            ctx.editor.move_cursors_horizontal(-1, select=True)
            return
        ctx.start_selection(buffer)
        if buffer.cursor_position > 0:
            buffer.cursor_position -= 1

    @ctx.bind("s-right", filter=editable_text_focus & ~ctx.has_completions_menu)
    def _s_right(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer and ctx.editor.multi_cursor_active():
            ctx.editor.move_cursors_horizontal(1, select=True)
            return
        ctx.start_selection(buffer)
        if buffer.cursor_position < len(buffer.text):
            buffer.cursor_position += 1

    @ctx.bind("s-up", filter=editor_command_focus)
    def _s_up(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_vertical(-1, select=True)
            return
        ctx.start_selection(buffer)
        buffer.cursor_position += buffer.document.get_cursor_up_position()

    @ctx.bind("s-down", filter=editor_command_focus)
    def _s_down(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if buffer is ctx.editor.buffer:
            ctx.editor.move_cursors_vertical(1, select=True)
            return
        ctx.start_selection(buffer)
        buffer.cursor_position += buffer.document.get_cursor_down_position()

    @ctx.bind("up", filter=editor_command_focus, note_activity=True)
    def _up(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=False):
            ctx.editor.reattach_scroll_to_cursor()
            return
        ctx.editor.move_cursors_vertical(-1)

    @ctx.bind(
        "down",
        filter=editor_command_focus,
        note_activity=True,
    )
    def _down(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        if _collapse_selection(buffer, to_end=True):
            ctx.editor.reattach_scroll_to_cursor()
            return
        ctx.editor.move_cursors_vertical(1)

    @ctx.bind("c-up", filter=editor_command_focus)
    @ctx.bind(
        "escape",
        "[",
        "1",
        ";",
        "5",
        "A",
        filter=editor_command_focus,
    )
    def _scroll_up(event: KeyPressEvent) -> None:
        ctx.editor.scroll_view(-1)

    @ctx.bind("c-down", filter=editor_command_focus)
    @ctx.bind(
        "escape",
        "[",
        "1",
        ";",
        "5",
        "B",
        filter=editor_command_focus,
    )
    def _scroll_down(event: KeyPressEvent) -> None:
        ctx.editor.scroll_view(1)

    @ctx.bind("c-pageup", filter=editor_command_focus)
    @ctx.bind(
        "escape",
        "[",
        "5",
        ";",
        "5",
        "~",
        filter=editor_command_focus,
    )
    def _scroll_page_up(event: KeyPressEvent) -> None:
        ctx.editor.scroll_view(-1, count=15)

    @ctx.bind("c-pagedown", filter=editor_command_focus)
    @ctx.bind(
        "escape",
        "[",
        "6",
        ";",
        "5",
        "~",
        filter=editor_command_focus,
    )
    def _scroll_page_down(event: KeyPressEvent) -> None:
        ctx.editor.scroll_view(1, count=15)

    @ctx.bind("escape", filter=editor_command_focus)
    def _escape_multi_cursor(event: KeyPressEvent) -> None:
        if ctx.editor.multi_cursor_active():
            ctx.editor.clear_multi_cursors()

    @ctx.bind_sequences(
        SHIFT_ALT_UP,
        filter=editor_command_focus,
        note_activity=True,
    )
    def _clone_below(event: KeyPressEvent) -> None:
        ctx.editor.clone_current_lines_or_selections(insert_above=False)

    @ctx.bind_sequences(
        SHIFT_ALT_DOWN,
        filter=editor_command_focus,
        note_activity=True,
    )
    def _clone_above(event: KeyPressEvent) -> None:
        ctx.editor.clone_current_lines_or_selections(insert_above=True)

    @ctx.bind_sequences(
        CTRL_ALT_UP,
        filter=editor_command_focus,
    )
    def _add_cursor_up(event: KeyPressEvent) -> None:
        ctx.editor.add_vertical_cursor(-1)

    @ctx.bind_sequences(
        CTRL_ALT_DOWN,
        filter=editor_command_focus,
    )
    def _add_cursor_down(event: KeyPressEvent) -> None:
        ctx.editor.add_vertical_cursor(1)

    @ctx.bind_sequences(
        CTRL_SHIFT_ALT_UP,
        filter=editor_command_focus,
    )
    def _expand_cursor_up(event: KeyPressEvent) -> None:
        ctx.editor.expand_or_shrink_vertical_cursors(-1)

    @ctx.bind_sequences(
        CTRL_SHIFT_ALT_DOWN,
        filter=editor_command_focus,
    )
    def _expand_cursor_down(event: KeyPressEvent) -> None:
        ctx.editor.expand_or_shrink_vertical_cursors(1)

    @ctx.bind("c-d", filter=editor_command_focus)
    def _select_next_occurrence(event: KeyPressEvent) -> None:
        ctx.editor.select_next_occurrence()

    @ctx.bind("c-l", filter=editor_command_focus)
    def _select_all_occurrences(event: KeyPressEvent) -> None:
        ctx.editor.select_all_occurrences()

    @ctx.bind("escape", "up", filter=editor_command_focus)
    def _move_line_up(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        document = buffer.document
        row = document.cursor_position_row
        if row > 0:
            lines = document.lines[:]
            lines[row - 1], lines[row] = lines[row], lines[row - 1]
            buffer.text = "\n".join(lines)
            buffer.cursor_position = buffer.document.translate_row_col_to_index(
                row - 1,
                document.cursor_position_col,
            )

    @ctx.bind("escape", "down", filter=editor_command_focus)
    def _move_line_down(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        document = buffer.document
        row = document.cursor_position_row
        if row < document.line_count - 1:
            lines = document.lines[:]
            lines[row + 1], lines[row] = lines[row], lines[row + 1]
            buffer.text = "\n".join(lines)
            buffer.cursor_position = buffer.document.translate_row_col_to_index(
                row + 1,
                document.cursor_position_col,
            )

    @ctx.bind("c-_", filter=editor_text_focus)
    def _toggle_comment(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        document = buffer.document
        active_context = get_active_editor_context(
            document.text,
            document.cursor_position,
        )

        prefix, suffix = (
            ("<!-- ", " -->")
            if not active_context.in_fenced_block
            else get_comment_syntax(active_context.language_key)
        )
        start_row, end_row = _get_selected_row_range(buffer)
        lines = document.lines
        target_lines = lines[start_row : end_row + 1]
        all_commented = True
        for line in target_lines:
            stripped = line.lstrip()
            if not stripped:
                continue
            if not stripped.startswith(prefix.strip()):
                all_commented = False
                break
            if suffix and not stripped.endswith(suffix.strip()):
                all_commented = False
                break

        new_lines = list(lines)
        for index in range(start_row, end_row + 1):
            line = new_lines[index]
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]
            if not stripped and not all_commented:
                continue
            if all_commented:
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix) :]
                elif stripped.startswith(prefix.strip()):
                    stripped = stripped[len(prefix.strip()) :]
                if suffix:
                    if stripped.endswith(suffix):
                        stripped = stripped[: -len(suffix)]
                    elif stripped.endswith(suffix.strip()):
                        stripped = stripped[: -len(suffix.strip())]
                new_lines[index] = indent + stripped
            else:
                new_lines[index] = indent + prefix + stripped + suffix

        cursor_row = document.cursor_position_row
        cursor_col = document.cursor_position_col
        buffer.text = "\n".join(new_lines)
        cursor_col = (
            max(0, cursor_col - len(prefix))
            if all_commented
            else cursor_col + len(prefix)
        )
        cursor_col = min(cursor_col, len(new_lines[cursor_row]))
        buffer.cursor_position = buffer.document.translate_row_col_to_index(
            cursor_row,
            cursor_col,
        )

    @ctx.bind("c-s", filter=editor_text_focus)
    def _save(event: KeyPressEvent) -> None:
        async def _do_save() -> None:
            ctx.editor.note_user_activity()
            issues = await ctx.editor.collect_save_issues()
            if issues:
                ctx.editor.activate_issue_mode(issues)
                event.app.invalidate()
                return

            ctx.editor.deactivate_issue_mode()
            ctx.editor.result = ctx.editor.buffer.text
            event.app.exit()

        asyncio.create_task(_do_save())

    @ctx.bind("c-q")
    @ctx.bind("f10")
    def _quit(event: KeyPressEvent) -> None:
        ctx.editor.open_quit_confirm()

"""Editing, clipboard, cursor movement, and save bindings"""

from __future__ import annotations

import asyncio
import re
import time

from prompt_toolkit.filters import has_selection
from prompt_toolkit.keys import Keys
from prompt_toolkit.selection import SelectionState

from ...core.context import get_comment_syntax
from .context import EditorBindingContext


def _get_selected_row_range(buffer) -> tuple[int, int]:
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


def register_editing_bindings(ctx: EditorBindingContext) -> None:
    """Register bindings for editing, selection, cursor movement, and save"""

    @ctx.bind("c-a", filter=ctx.text_focus)
    def _select_all(event) -> None:
        buffer = event.app.current_buffer
        buffer.selection_state = SelectionState(original_cursor_position=0)
        buffer.cursor_position = len(buffer.text)

    @ctx.bind("c-c", filter=ctx.text_focus)
    def _copy(event) -> None:
        buffer = event.app.current_buffer
        if buffer.selection_state:
            data = buffer.copy_selection()
            event.app.clipboard.set_data(data)

    @ctx.bind("c-x", filter=ctx.text_focus)
    def _cut(event) -> None:
        buffer = event.app.current_buffer
        if buffer.selection_state:
            data = buffer.cut_selection()
            event.app.clipboard.set_data(data)
            buffer.selection_state = None

    @ctx.bind("c-v", filter=ctx.text_focus)
    def _paste(event) -> None:
        buffer = event.app.current_buffer
        data = event.app.clipboard.get_data()
        if data and data.text:
            ctx.editor.paste_text(buffer, data.text)

    @ctx.bind("s-insert", filter=ctx.text_focus)
    @ctx.bind("c-s-insert", filter=ctx.text_focus)
    def _paste_system_clipboard(event) -> None:
        ctx.schedule_system_clipboard_paste()

    @ctx.bind("escape", "[", "2", ";", "2", "~", filter=ctx.text_focus)
    @ctx.bind("escape", "[", "2", ";", "6", "~", filter=ctx.text_focus)
    def _paste_system_clipboard_xterm_insert(event) -> None:
        ctx.schedule_system_clipboard_paste()

    @ctx.bind(Keys.BracketedPaste, filter=ctx.text_focus)
    def _paste_terminal_payload(event) -> None:
        buffer = event.app.current_buffer
        text = event.data.replace("\r\n", "\n").replace("\r", "\n")
        ctx.editor.paste_text(buffer, text)

    @ctx.bind("c-z", filter=ctx.text_focus)
    def _undo(event) -> None:
        event.app.current_buffer.undo()

    @ctx.bind("c-y", filter=ctx.text_focus, eager=True)
    def _redo(event) -> None:
        event.app.current_buffer.redo()

    @ctx.bind("home", filter=ctx.text_focus, note_activity=True)
    def _home(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        buffer.cursor_position += ctx.get_home_position(buffer.document)

    @ctx.bind("end", filter=ctx.text_focus, note_activity=True)
    def _end(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        buffer.cursor_position += buffer.document.get_end_of_line_position()

    @ctx.bind("pageup", filter=ctx.editor_focus)
    def _pageup(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        buffer.cursor_position += buffer.document.get_cursor_up_position(count=15)

    @ctx.bind("pagedown", filter=ctx.editor_focus)
    def _pagedown(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        buffer.cursor_position += buffer.document.get_cursor_down_position(count=15)

    @ctx.bind("c-home", filter=ctx.text_focus, note_activity=True)
    def _c_home(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        buffer.cursor_position = 0

    @ctx.bind("c-end", filter=ctx.text_focus, note_activity=True)
    def _c_end(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        buffer.cursor_position = len(buffer.text)

    @ctx.bind("c-left", filter=ctx.text_focus)
    def _c_left(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        position = buffer.document.find_previous_word_beginning()
        buffer.cursor_position += (
            position if position is not None else -buffer.cursor_position
        )

    @ctx.bind("c-right", filter=ctx.text_focus)
    def _c_right(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        position = buffer.document.find_next_word_beginning()
        if position is not None:
            buffer.cursor_position += position
        else:
            buffer.cursor_position = len(buffer.text)

    @ctx.bind("s-home", filter=ctx.text_focus)
    def _s_home(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        buffer.cursor_position += ctx.get_home_position(buffer.document)

    @ctx.bind("s-end", filter=ctx.text_focus)
    def _s_end(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        buffer.cursor_position += buffer.document.get_end_of_line_position()

    @ctx.bind("s-pageup", filter=ctx.editor_focus)
    def _s_pageup(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        buffer.cursor_position += buffer.document.get_cursor_up_position(count=15)

    @ctx.bind("s-pagedown", filter=ctx.editor_focus)
    def _s_pagedown(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        buffer.cursor_position += buffer.document.get_cursor_down_position(count=15)

    @ctx.bind("s-c-home", filter=ctx.text_focus)
    def _s_c_home(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        buffer.cursor_position = 0

    @ctx.bind("s-c-end", filter=ctx.text_focus)
    def _s_c_end(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        buffer.cursor_position = len(buffer.text)

    @ctx.bind("s-c-left", filter=ctx.text_focus)
    def _s_c_left(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        position = buffer.document.find_previous_word_beginning()
        buffer.cursor_position += (
            position if position is not None else -buffer.cursor_position
        )

    @ctx.bind("s-c-right", filter=ctx.text_focus)
    def _s_c_right(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        position = buffer.document.find_next_word_beginning()
        if position is not None:
            buffer.cursor_position += position
        else:
            buffer.cursor_position = len(buffer.text)

    @ctx.bind("c-w", filter=ctx.text_focus)
    def _delete_previous_word(event) -> None:
        buffer = event.current_buffer
        if buffer.selection_state:
            buffer.cut_selection()
            buffer.selection_state = None
            return

        position = buffer.document.find_previous_word_beginning()
        if position is not None:
            buffer.delete_before_cursor(count=-position)
        else:
            buffer.delete_before_cursor(count=buffer.cursor_position)

    @ctx.bind("c-delete", filter=ctx.text_focus)
    def _delete_next_word(event) -> None:
        buffer = event.current_buffer
        if buffer.selection_state:
            buffer.cut_selection()
            buffer.selection_state = None
            return

        position = buffer.document.find_next_word_beginning()
        if position is not None:
            buffer.delete(count=position)
        else:
            buffer.delete(count=len(buffer.text) - buffer.cursor_position)

    @ctx.bind("backspace", filter=ctx.text_focus & has_selection)
    @ctx.bind("delete", filter=ctx.text_focus & has_selection)
    def _delete_selection(event) -> None:
        buffer = event.current_buffer
        buffer.cut_selection()
        buffer.selection_state = None

    @ctx.bind("<any>", filter=ctx.text_focus & has_selection)
    def _type_over_selection(event) -> None:
        buffer = event.current_buffer
        if event.data and event.data.isprintable():
            buffer.cut_selection()
            buffer.selection_state = None
            buffer.insert_text(event.data)
        else:
            buffer.selection_state = None

    # Track entry time to distinguish simulated terminal paste logic from real typing.
    last_enter_time = [0.0]

    @ctx.bind("enter", filter=ctx.editor_focus & ~ctx.has_completions_menu)
    def _smart_enter(event) -> None:
        now = time.time()
        is_paste = (now - last_enter_time[0]) < 0.05
        last_enter_time[0] = now

        buffer = event.current_buffer
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

    @ctx.bind("tab", filter=ctx.editor_focus & ~ctx.has_completions_menu)
    def _tab(event) -> None:
        buffer = event.current_buffer
        document = buffer.document
        indent_str = ctx.detect_indent_style(document)

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

    @ctx.bind("s-tab", filter=ctx.editor_focus & ~ctx.has_completions_menu)
    def _s_tab(event) -> None:
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
    def _left(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        if buffer.cursor_position > 0:
            buffer.cursor_position -= 1

    @ctx.bind(
        "right",
        filter=ctx.text_focus & ~ctx.has_completions_menu,
        note_activity=True,
    )
    def _right(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        if buffer.cursor_position < len(buffer.text):
            buffer.cursor_position += 1

    @ctx.bind("s-left", filter=ctx.text_focus & ~ctx.has_completions_menu)
    def _s_left(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        if buffer.cursor_position > 0:
            buffer.cursor_position -= 1

    @ctx.bind("s-right", filter=ctx.text_focus & ~ctx.has_completions_menu)
    def _s_right(event) -> None:
        buffer = event.current_buffer
        ctx.start_selection(buffer)
        if buffer.cursor_position < len(buffer.text):
            buffer.cursor_position += 1

    @ctx.bind(
        "up", filter=ctx.editor_focus & ~ctx.has_completions_menu, note_activity=True
    )
    def _up(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        buffer.cursor_position += buffer.document.get_cursor_up_position(count=1)

    @ctx.bind(
        "down",
        filter=ctx.editor_focus & ~ctx.has_completions_menu,
        note_activity=True,
    )
    def _down(event) -> None:
        buffer = event.current_buffer
        buffer.selection_state = None
        buffer.cursor_position += buffer.document.get_cursor_down_position(count=1)

    @ctx.bind("escape", "up", filter=ctx.editor_focus & ~ctx.has_completions_menu)
    def _move_line_up(event) -> None:
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

    @ctx.bind("escape", "down", filter=ctx.editor_focus & ~ctx.has_completions_menu)
    def _move_line_down(event) -> None:
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

    @ctx.bind("c-_", filter=ctx.editor_focus)
    def _toggle_comment(event) -> None:
        buffer = event.current_buffer
        document = buffer.document
        lines_before = document.lines[: document.cursor_position_row]
        in_block = False
        language = "markdown"
        for line in lines_before:
            if line.strip().startswith("```"):
                if in_block:
                    in_block = False
                    language = "markdown"
                else:
                    in_block = True
                    language = line.strip()[3:].strip().lower()

        prefix, suffix = (
            ("<!-- ", " -->") if not in_block else get_comment_syntax(language)
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

    @ctx.bind("c-s", filter=~ctx.search_widget_focus)
    def _save(event) -> None:
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
    def _quit(event) -> None:
        ctx.editor.open_quit_confirm()

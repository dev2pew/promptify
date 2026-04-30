"""Keybinding registration for standard and custom editor shortcuts"""

import asyncio
import pyperclip
import re
import time
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition, has_selection, has_focus
from prompt_toolkit.keys import Keys
from prompt_toolkit.selection import SelectionState
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

from ..core.context import get_comment_syntax


def detect_indent_style(document: Document) -> str:
    """Detect the indentation style used in the current document"""
    for line in document.lines:
        if line.startswith("\t"):
            return "\t"
        if line.startswith("  ") and not line.startswith("   "):
            return "  "
        if line.startswith("    "):
            return "    "
    return "    "


def setup_keybindings(editor) -> KeyBindings:
    custom_bindings = KeyBindings()

    @Condition
    def is_help_visible() -> bool:
        return editor.help_visible

    @Condition
    def is_err_visible() -> bool:
        return editor.err_visible

    @Condition
    def is_issue_mode_active() -> bool:
        return editor.issue_mode_active and editor.err_visible

    @Condition
    def has_completions_menu() -> bool:
        b = get_app().current_buffer
        return b.complete_state is not None and len(b.complete_state.completions) > 0

    @Condition
    def is_completion_selected() -> bool:
        b = get_app().current_buffer
        return (
            b.complete_state is not None
            and b.complete_state.current_completion is not None
        )

    editor_focus = has_focus(editor.buffer)
    search_focus = has_focus(editor.search_buffer)
    text_focus = editor_focus | search_focus

    def get_home_position(document: Document) -> int:
        first_non_ws = document.get_start_of_line_position(after_whitespace=True)
        if first_non_ws == 0:
            return document.get_start_of_line_position(after_whitespace=False)
        return first_non_ws

    def _start_sel(b: Buffer) -> None:
        if b.selection_state is None:
            b.selection_state = SelectionState(
                original_cursor_position=b.cursor_position
            )

    def _schedule_system_clipboard_paste() -> None:
        b = get_app().current_buffer

        async def _do_paste():
            try:
                text = await asyncio.to_thread(pyperclip.paste)
            except Exception:
                editor.set_passive_status(
                    editor.get_text("clipboard_unavailable", "clipboard unavailable")
                )
                return

            if text:
                editor.paste_text(b, text)
                get_app().invalidate()

        asyncio.create_task(_do_paste())

    @custom_bindings.add("f1")
    @custom_bindings.add("c-g")
    def _toggle_help(event) -> None:
        editor.note_user_activity()
        editor.toggle_help()

    @custom_bindings.add("c-f", filter=editor_focus | search_focus, eager=True)
    def _search(event) -> None:
        """Open the custom search bar without entering prompt-toolkit search mode"""
        editor.open_search()

    @custom_bindings.add("escape", filter=is_help_visible)
    @custom_bindings.add("enter", filter=is_help_visible)
    def _close_help_esc(event) -> None:
        editor.note_user_activity()
        editor.close_help()

    @custom_bindings.add("escape", filter=is_err_visible)
    def _close_err(event) -> None:
        editor.note_user_activity()
        if editor.issue_mode_active:
            editor.deactivate_issue_mode()
        else:
            editor.err_visible = False
            event.app.layout.focus(editor.main_window)

    @custom_bindings.add("enter", filter=is_issue_mode_active)
    @custom_bindings.add("c-n", filter=is_issue_mode_active)
    def _next_issue(event) -> None:
        editor.note_user_activity()
        editor.step_issue(1)

    @custom_bindings.add("c-r", filter=is_issue_mode_active)
    @custom_bindings.add("c-p", filter=is_issue_mode_active)
    def _previous_issue(event) -> None:
        editor.note_user_activity()
        editor.step_issue(-1)

    @custom_bindings.add("enter", filter=is_err_visible & ~is_issue_mode_active)
    def _dismiss_err(event) -> None:
        editor.note_user_activity()
        editor.err_visible = False
        event.app.layout.focus(editor.main_window)

    @custom_bindings.add("up", filter=editor_focus & has_completions_menu)
    def _up_completion(event) -> None:
        event.current_buffer.complete_previous()

    @custom_bindings.add("down", filter=editor_focus & has_completions_menu)
    def _down_completion(event) -> None:
        event.current_buffer.complete_next()

    @custom_bindings.add(
        "enter",
        filter=editor_focus & has_completions_menu & ~is_completion_selected,
    )
    def _(event) -> None:
        b = event.current_buffer
        if b.complete_state and b.complete_state.completions:
            completion = b.complete_state.completions[0]
            b.apply_completion(completion)

    @custom_bindings.add(
        "enter", filter=editor_focus & has_completions_menu & is_completion_selected
    )
    def _(event) -> None:
        b = event.current_buffer
        if b.complete_state and b.complete_state.current_completion:
            b.apply_completion(b.complete_state.current_completion)

    @custom_bindings.add("escape", filter=editor_focus & has_completions_menu)
    def _(event) -> None:
        event.current_buffer.cancel_completion()

    @custom_bindings.add("escape", filter=search_focus)
    def _close_search(event) -> None:
        editor.note_user_activity()
        editor.close_search()

    @custom_bindings.add("enter", filter=search_focus)
    def _search_next(event) -> None:
        editor.note_user_activity()
        editor.search_step(1)
        event.app.invalidate()

    @custom_bindings.add("c-r", filter=search_focus)
    def _search_previous(event) -> None:
        editor.note_user_activity()
        editor.search_step(-1)
        event.app.invalidate()

    @custom_bindings.add("c-a", filter=text_focus)
    def _select_all(event) -> None:
        b = event.app.current_buffer
        b.selection_state = SelectionState(original_cursor_position=0)
        b.cursor_position = len(b.text)

    @custom_bindings.add("c-c", filter=text_focus)
    def _copy(event) -> None:
        b = event.app.current_buffer
        if b.selection_state:
            data = b.copy_selection()
            event.app.clipboard.set_data(data)

    @custom_bindings.add("c-x", filter=text_focus)
    def _cut(event) -> None:
        b = event.app.current_buffer
        if b.selection_state:
            data = b.cut_selection()
            event.app.clipboard.set_data(data)
            b.selection_state = None

    @custom_bindings.add("c-v", filter=text_focus)
    def _paste(event) -> None:
        b = event.app.current_buffer
        data = event.app.clipboard.get_data()
        if data and data.text:
            editor.paste_text(b, data.text)

    @custom_bindings.add("s-insert", filter=text_focus)
    @custom_bindings.add("c-s-insert", filter=text_focus)
    def _paste_system_clipboard(event) -> None:
        _schedule_system_clipboard_paste()

    @custom_bindings.add("escape", "[", "2", ";", "2", "~", filter=text_focus)
    @custom_bindings.add("escape", "[", "2", ";", "6", "~", filter=text_focus)
    def _paste_system_clipboard_xterm_insert(event) -> None:
        _schedule_system_clipboard_paste()

    @custom_bindings.add(Keys.BracketedPaste, filter=text_focus)
    def _paste_terminal_payload(event) -> None:
        b = event.app.current_buffer
        text = event.data.replace("\r\n", "\n").replace("\r", "\n")
        editor.paste_text(b, text)

    @custom_bindings.add("c-z", filter=text_focus)
    def _undo(event) -> None:
        event.app.current_buffer.undo()

    @custom_bindings.add("c-y", filter=text_focus, eager=True)
    def _redo(event) -> None:
        event.app.current_buffer.redo()

    @custom_bindings.add("home", filter=text_focus)
    def _home(event) -> None:
        editor.note_user_activity()
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position += get_home_position(b.document)

    @custom_bindings.add("end", filter=text_focus)
    def _end(event) -> None:
        editor.note_user_activity()
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position += b.document.get_end_of_line_position()

    @custom_bindings.add("pageup", filter=editor_focus)
    def _pageup(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position += b.document.get_cursor_up_position(count=15)

    @custom_bindings.add("pagedown", filter=editor_focus)
    def _pagedown(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position += b.document.get_cursor_down_position(count=15)

    @custom_bindings.add("c-home", filter=text_focus)
    def _c_home(event) -> None:
        editor.note_user_activity()
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position = 0

    @custom_bindings.add("c-end", filter=text_focus)
    def _c_end(event) -> None:
        editor.note_user_activity()
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position = len(b.text)

    @custom_bindings.add("c-left", filter=text_focus)
    def _c_left(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        pos = b.document.find_previous_word_beginning()
        if pos is not None:
            b.cursor_position += pos
        else:
            b.cursor_position = 0

    @custom_bindings.add("c-right", filter=text_focus)
    def _c_right(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        pos = b.document.find_next_word_beginning()
        if pos is not None:
            b.cursor_position += pos
        else:
            b.cursor_position = len(b.text)

    @custom_bindings.add("s-home", filter=text_focus)
    def _s_home(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position += get_home_position(b.document)

    @custom_bindings.add("s-end", filter=text_focus)
    def _s_end(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position += b.document.get_end_of_line_position()

    @custom_bindings.add("s-pageup", filter=editor_focus)
    def _s_pageup(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position += b.document.get_cursor_up_position(count=15)

    @custom_bindings.add("s-pagedown", filter=editor_focus)
    def _s_pagedown(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position += b.document.get_cursor_down_position(count=15)

    @custom_bindings.add("s-c-home", filter=text_focus)
    def _s_c_home(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position = 0

    @custom_bindings.add("s-c-end", filter=text_focus)
    def _s_c_end(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position = len(b.text)

    @custom_bindings.add("s-c-left", filter=text_focus)
    def _s_c_left(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        pos = b.document.find_previous_word_beginning()
        if pos is not None:
            b.cursor_position += pos
        else:
            b.cursor_position = 0

    @custom_bindings.add("s-c-right", filter=text_focus)
    def _s_c_right(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        pos = b.document.find_next_word_beginning()
        if pos is not None:
            b.cursor_position += pos
        else:
            b.cursor_position = len(b.text)

    @custom_bindings.add("c-w", filter=text_focus)
    def _c_w(event) -> None:
        b = event.current_buffer
        if b.selection_state:
            b.cut_selection()
            b.selection_state = None
        else:
            pos = b.document.find_previous_word_beginning()
            if pos is not None:
                b.delete_before_cursor(count=-pos)
            else:
                b.delete_before_cursor(count=b.cursor_position)

    @custom_bindings.add("c-delete", filter=text_focus)
    def _c_delete(event) -> None:
        b = event.current_buffer
        if b.selection_state:
            b.cut_selection()
            b.selection_state = None
        else:
            pos = b.document.find_next_word_beginning()
            if pos is not None:
                b.delete(count=pos)
            else:
                b.delete(count=len(b.text) - b.cursor_position)

    @custom_bindings.add("backspace", filter=text_focus & has_selection)
    @custom_bindings.add("delete", filter=text_focus & has_selection)
    def _delete_selection(event) -> None:
        b = event.current_buffer
        b.cut_selection()
        b.selection_state = None

    @custom_bindings.add("<any>", filter=text_focus & has_selection)
    def _type_over_selection(event) -> None:
        b = event.current_buffer
        if event.data and event.data.isprintable():
            b.cut_selection()
            b.selection_state = None
            b.insert_text(event.data)
        else:
            b.selection_state = None

    # TRACK ENTRY TIME TO DISTINGUISH SIMULATED TERMINAL PASTE LOGIC FROM GENUINE TYPING
    _last_enter_time = [0.0]

    @custom_bindings.add("enter", filter=editor_focus & ~has_completions_menu)
    def _smart_enter(event) -> None:
        now = time.time()
        is_paste = (now - _last_enter_time[0]) < 0.05
        _last_enter_time[0] = now

        b = event.current_buffer
        if b.selection_state:
            b.cut_selection()
            b.selection_state = None

        if is_paste:
            # SIMULATED PASTE TRIGGERS (E.G. RIGHT CLICK) HAPPEN TOO QUICKLY;
            # BYPASS FORMATTING LOGIC TO AVOID EXPONENTIAL STAIRCASE INDENTING
            b.insert_text("\n")
        else:
            doc = b.document
            indent_str = detect_indent_style(doc)
            current_line = doc.current_line
            indent_match = re.match(r"^(\s*)", current_line)
            indent = indent_match.group(1) if indent_match else ""

            # PREDICT INDENTATION DEPTH
            if current_line.rstrip().endswith((":")):
                indent += indent_str
            elif current_line.rstrip().endswith(("{", "[", "(")):
                indent += indent_str

            b.insert_text("\n" + indent)

    @custom_bindings.add("tab", filter=editor_focus & ~has_completions_menu)
    def _tab(event) -> None:
        b = event.current_buffer
        doc = b.document
        indent_str = detect_indent_style(doc)

        if b.selection_state:
            start_row = doc.translate_index_to_position(
                b.selection_state.original_cursor_position
            )[0]
            end_row = doc.cursor_position_row
            if start_row > end_row:
                start_row, end_row = end_row, start_row

            lines = doc.lines[:]
            for i in range(start_row, end_row + 1):
                lines[i] = indent_str + lines[i]

            cursor_row = doc.cursor_position_row
            cursor_col = doc.cursor_position_col
            b.text = "\n".join(lines)

            # REPOSITION THE CURSOR SAFELY RELATIVE TO ITS OLD COLUMN
            new_col = cursor_col + len(indent_str)
            b.cursor_position = b.document.translate_row_col_to_index(
                cursor_row, new_col
            )
        else:
            b.insert_text(indent_str)

    @custom_bindings.add("s-tab", filter=editor_focus & ~has_completions_menu)
    def _s_tab(event) -> None:
        b = event.current_buffer
        doc = b.document
        indent_str = detect_indent_style(doc)
        indent_len = len(indent_str)

        if b.selection_state:
            start_row = doc.translate_index_to_position(
                b.selection_state.original_cursor_position
            )[0]
            end_row = doc.cursor_position_row
            if start_row > end_row:
                start_row, end_row = end_row, start_row
        else:
            start_row = end_row = doc.cursor_position_row

        lines = doc.lines[:]
        cursor_col_offset = 0

        for i in range(start_row, end_row + 1):
            line = lines[i]
            if line.startswith(indent_str):
                lines[i] = line[indent_len:]
                if i == end_row:
                    cursor_col_offset = -indent_len
            elif line.startswith("\t"):
                lines[i] = line[1:]
                if i == end_row:
                    cursor_col_offset = -1
            elif line.startswith(" "):
                spaces = len(line) - len(line.lstrip(" "))
                to_remove = min(spaces, indent_len)
                lines[i] = line[to_remove:]
                if i == end_row:
                    cursor_col_offset = -to_remove

        cursor_row = doc.cursor_position_row
        cursor_col = doc.cursor_position_col
        b.text = "\n".join(lines)

        # REPOSITION THE CURSOR SAFELY RELATIVE TO ITS OLD COLUMN
        new_col = max(0, cursor_col + cursor_col_offset)
        b.cursor_position = b.document.translate_row_col_to_index(cursor_row, new_col)

    @custom_bindings.add("left", filter=text_focus & ~has_completions_menu)
    def _left(event) -> None:
        editor.note_user_activity()
        b = event.current_buffer
        b.selection_state = None
        if b.cursor_position > 0:
            b.cursor_position -= 1

    @custom_bindings.add("right", filter=text_focus & ~has_completions_menu)
    def _right(event) -> None:
        editor.note_user_activity()
        b = event.current_buffer
        b.selection_state = None
        if b.cursor_position < len(b.text):
            b.cursor_position += 1

    @custom_bindings.add("s-left", filter=text_focus & ~has_completions_menu)
    def _s_left(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        if b.cursor_position > 0:
            b.cursor_position -= 1

    @custom_bindings.add("s-right", filter=text_focus & ~has_completions_menu)
    def _s_right(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        if b.cursor_position < len(b.text):
            b.cursor_position += 1

    @custom_bindings.add("up", filter=editor_focus & ~has_completions_menu)
    def _up(event) -> None:
        editor.note_user_activity()
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position += b.document.get_cursor_up_position(count=1)

    @custom_bindings.add("down", filter=editor_focus & ~has_completions_menu)
    def _down(event) -> None:
        editor.note_user_activity()
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position += b.document.get_cursor_down_position(count=1)

    @custom_bindings.add("escape", "up", filter=editor_focus & ~has_completions_menu)
    def _move_line_up(event) -> None:
        b = event.current_buffer
        doc = b.document
        row = doc.cursor_position_row
        if row > 0:
            lines = doc.lines[:]
            lines[row - 1], lines[row] = lines[row], lines[row - 1]
            col = doc.cursor_position_col
            b.text = "\n".join(lines)
            b.cursor_position = b.document.translate_row_col_to_index(row - 1, col)

    @custom_bindings.add("escape", "down", filter=editor_focus & ~has_completions_menu)
    def _move_line_down(event) -> None:
        b = event.current_buffer
        doc = b.document
        row = doc.cursor_position_row
        if row < doc.line_count - 1:
            lines = doc.lines[:]
            lines[row + 1], lines[row] = lines[row], lines[row + 1]
            col = doc.cursor_position_col
            b.text = "\n".join(lines)
            b.cursor_position = b.document.translate_row_col_to_index(row + 1, col)

    @custom_bindings.add("c-_", filter=editor_focus)
    def _toggle_comment(event) -> None:
        b = event.current_buffer
        doc = b.document

        lines_before = doc.lines[: doc.cursor_position_row]
        in_block = False
        lang = "markdown"
        for line in lines_before:
            if line.strip().startswith("```"):
                if in_block:
                    in_block = False
                    lang = "markdown"
                else:
                    in_block = True
                    lang = line.strip()[3:].strip().lower()

        if not in_block:
            prefix, suffix = "<!-- ", " -->"
        else:
            prefix, suffix = get_comment_syntax(lang)

        if b.selection_state:
            start_row = doc.translate_index_to_position(
                b.selection_state.original_cursor_position
            )[0]
            end_row = doc.cursor_position_row
            if start_row > end_row:
                start_row, end_row = end_row, start_row
        else:
            start_row = end_row = doc.cursor_position_row

        lines = doc.lines
        target_lines = lines[start_row : end_row + 1]

        all_commented = True
        for line in target_lines:
            s = line.lstrip()
            if not s:
                continue
            if not s.startswith(prefix.strip()):
                all_commented = False
                break
            if suffix and not s.endswith(suffix.strip()):
                all_commented = False
                break

        new_lines = list(lines)
        for i in range(start_row, end_row + 1):
            line = new_lines[i]
            s = line.lstrip()
            indent = line[: len(line) - len(s)]

            if not s and not all_commented:
                continue

            if all_commented:
                if s.startswith(prefix):
                    s = s[len(prefix) :]
                elif s.startswith(prefix.strip()):
                    s = s[len(prefix.strip()) :]

                if suffix:
                    if s.endswith(suffix):
                        s = s[: -len(suffix)]
                    elif s.endswith(suffix.strip()):
                        s = s[: -len(suffix.strip())]
                new_lines[i] = indent + s
            else:
                new_lines[i] = indent + prefix + s + suffix

        cursor_row = doc.cursor_position_row
        cursor_col = doc.cursor_position_col

        b.text = "\n".join(new_lines)

        if all_commented:
            cursor_col = max(0, cursor_col - len(prefix))
        else:
            cursor_col += len(prefix)

        new_line_len = len(new_lines[cursor_row])
        cursor_col = min(cursor_col, new_line_len)

        b.cursor_position = b.document.translate_row_col_to_index(
            cursor_row, cursor_col
        )

    @custom_bindings.add("c-s", filter=~search_focus)
    def _save(event) -> None:
        async def _do_save():
            editor.note_user_activity()
            issues = await editor.collect_save_issues()
            if issues:
                editor.activate_issue_mode(issues)
                event.app.invalidate()
                return

            editor.deactivate_issue_mode()
            editor.result = editor.buffer.text
            event.app.exit()

        asyncio.create_task(_do_save())

    @custom_bindings.add("c-q")
    def _quit(event) -> None:
        editor.result = None
        event.app.exit()

    return custom_bindings

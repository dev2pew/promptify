import asyncio
import aiofiles
import re
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition, has_selection, has_focus
from prompt_toolkit.selection import SelectionState
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

from .constants import COMMENT_SYNTAX


def setup_keybindings(editor) -> KeyBindings:
    custom_bindings = KeyBindings()

    @Condition
    def is_help_visible() -> bool:
        return editor.help_visible

    @Condition
    def is_error_visible() -> bool:
        return editor.error_visible

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

    @custom_bindings.add("f1")
    @custom_bindings.add("c-g")
    def _toggle_help(event) -> None:
        editor.help_visible = not editor.help_visible
        if editor.help_visible:
            event.app.layout.focus(editor.help_window)
        else:
            event.app.layout.focus(editor.main_window)

    @custom_bindings.add("escape", filter=is_help_visible)
    @custom_bindings.add("enter", filter=is_help_visible)
    def _close_help_esc(event) -> None:
        editor.help_visible = False
        event.app.layout.focus(editor.main_window)

    @custom_bindings.add("escape", filter=is_error_visible)
    @custom_bindings.add("enter", filter=is_error_visible)
    def _close_error(event) -> None:
        editor.error_visible = False
        event.app.layout.focus(editor.main_window)

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

    @custom_bindings.add("c-a", filter=editor_focus)
    def _select_all(event) -> None:
        b = event.app.current_buffer
        b.selection_state = SelectionState(original_cursor_position=0)
        b.cursor_position = len(b.text)

    @custom_bindings.add("c-c", filter=editor_focus)
    def _copy(event) -> None:
        b = event.app.current_buffer
        if b.selection_state:
            data = b.copy_selection()
            event.app.clipboard.set_data(data)

    @custom_bindings.add("c-x", filter=editor_focus)
    def _cut(event) -> None:
        b = event.app.current_buffer
        if b.selection_state:
            data = b.cut_selection()
            event.app.clipboard.set_data(data)
            b.selection_state = None

    @custom_bindings.add("c-v", filter=editor_focus)
    def _paste(event) -> None:
        b = event.app.current_buffer
        if b.selection_state:
            b.cut_selection()
            b.selection_state = None
        b.paste_clipboard_data(event.app.clipboard.get_data())

    @custom_bindings.add("c-z", filter=editor_focus)
    def _undo(event) -> None:
        event.app.current_buffer.undo()

    @custom_bindings.add("c-y", filter=editor_focus)
    def _redo(event) -> None:
        event.app.current_buffer.redo()

    @custom_bindings.add("home", filter=editor_focus)
    def _home(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position += get_home_position(b.document)

    @custom_bindings.add("end", filter=editor_focus)
    def _end(event) -> None:
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

    @custom_bindings.add("c-home", filter=editor_focus)
    def _c_home(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position = 0

    @custom_bindings.add("c-end", filter=editor_focus)
    def _c_end(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position = len(b.text)

    @custom_bindings.add("c-left", filter=editor_focus)
    def _c_left(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        pos = b.document.find_previous_word_beginning()
        if pos is not None:
            b.cursor_position += pos
        else:
            b.cursor_position = 0

    @custom_bindings.add("c-right", filter=editor_focus)
    def _c_right(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        pos = b.document.find_next_word_beginning()
        if pos is not None:
            b.cursor_position += pos
        else:
            b.cursor_position = len(b.text)

    @custom_bindings.add("s-home", filter=editor_focus)
    def _s_home(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position += get_home_position(b.document)

    @custom_bindings.add("s-end", filter=editor_focus)
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

    @custom_bindings.add("s-c-home", filter=editor_focus)
    def _s_c_home(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position = 0

    @custom_bindings.add("s-c-end", filter=editor_focus)
    def _s_c_end(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        b.cursor_position = len(b.text)

    @custom_bindings.add("s-c-left", filter=editor_focus)
    def _s_c_left(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        pos = b.document.find_previous_word_beginning()
        if pos is not None:
            b.cursor_position += pos
        else:
            b.cursor_position = 0

    @custom_bindings.add("s-c-right", filter=editor_focus)
    def _s_c_right(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        pos = b.document.find_next_word_beginning()
        if pos is not None:
            b.cursor_position += pos
        else:
            b.cursor_position = len(b.text)

    @custom_bindings.add("c-w", filter=editor_focus)
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

    @custom_bindings.add("c-delete", filter=editor_focus)
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

    @custom_bindings.add("backspace", filter=editor_focus & has_selection)
    @custom_bindings.add("delete", filter=editor_focus & has_selection)
    def _delete_selection(event) -> None:
        b = event.current_buffer
        b.cut_selection()
        b.selection_state = None

    @custom_bindings.add("<any>", filter=editor_focus & has_selection)
    def _type_over_selection(event) -> None:
        b = event.current_buffer
        if event.data and event.data.isprintable():
            b.cut_selection()
            b.selection_state = None
            b.insert_text(event.data)
        else:
            b.selection_state = None

    @custom_bindings.add(
        "enter", filter=editor_focus & has_selection & ~has_completions_menu
    )
    def _enter_over_selection(event) -> None:
        b = event.current_buffer
        b.cut_selection()
        b.selection_state = None
        b.insert_text("\n")

    @custom_bindings.add("tab", filter=editor_focus & ~has_completions_menu)
    def _tab(event) -> None:
        b = event.current_buffer
        doc = b.document
        if b.selection_state:
            start_row = doc.translate_index_to_position(
                b.selection_state.original_cursor_position
            )[0]
            end_row = doc.cursor_position_row
            if start_row > end_row:
                start_row, end_row = end_row, start_row

            lines = doc.lines[:]
            for i in range(start_row, end_row + 1):
                lines[i] = "    " + lines[i]

            cursor_pos = b.cursor_position
            b.text = "\n".join(lines)
            b.cursor_position = cursor_pos + 4 * (end_row - start_row + 1)
        else:
            b.insert_text("    ")

    @custom_bindings.add("s-tab", filter=editor_focus & ~has_completions_menu)
    def _s_tab(event) -> None:
        b = event.current_buffer
        doc = b.document
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
        removed_total = 0
        for i in range(start_row, end_row + 1):
            if lines[i].startswith("    "):
                lines[i] = lines[i][4:]
                removed_total += 4
            elif lines[i].startswith("\t"):
                lines[i] = lines[i][1:]
                removed_total += 1
            elif lines[i].startswith(" "):
                spaces = len(lines[i]) - len(lines[i].lstrip(" "))
                to_remove = min(spaces, 4)
                lines[i] = lines[i][to_remove:]
                removed_total += to_remove

        cursor_pos = b.cursor_position
        b.text = "\n".join(lines)
        b.cursor_position = max(0, cursor_pos - removed_total)

    @custom_bindings.add("left", filter=editor_focus & ~has_completions_menu)
    def _left(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        if b.cursor_position > 0:
            b.cursor_position -= 1

    @custom_bindings.add("right", filter=editor_focus & ~has_completions_menu)
    def _right(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        if b.cursor_position < len(b.text):
            b.cursor_position += 1

    @custom_bindings.add("s-left", filter=editor_focus & ~has_completions_menu)
    def _s_left(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        if b.cursor_position > 0:
            b.cursor_position -= 1

    @custom_bindings.add("s-right", filter=editor_focus & ~has_completions_menu)
    def _s_right(event) -> None:
        b = event.current_buffer
        _start_sel(b)
        if b.cursor_position < len(b.text):
            b.cursor_position += 1

    @custom_bindings.add("up", filter=editor_focus & ~has_completions_menu)
    def _up(event) -> None:
        b = event.current_buffer
        b.selection_state = None
        b.cursor_position += b.document.get_cursor_up_position(count=1)

    @custom_bindings.add("down", filter=editor_focus & ~has_completions_menu)
    def _down(event) -> None:
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
            prefix, suffix = ("<!-- ", " -->")
        else:
            prefix, suffix = COMMENT_SYNTAX.get(lang, ("# ", ""))

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

    @custom_bindings.add("c-s")
    def _save(event) -> None:
        async def _do_save():
            text = editor.buffer.text
            matches = re.findall(r"<@symbol:([^>:]+):([^>]+)>", text)
            for path, symbol in matches:
                file_matches = editor.indexer.find_matches(path)
                if not file_matches:
                    continue
                meta = file_matches[0]
                try:
                    async with aiofiles.open(
                        meta.path, "r", encoding="utf-8", errors="replace"
                    ) as f:
                        content = await f.read()
                    from .extractor import SymbolExtractor

                    extractor = SymbolExtractor(content, meta.path.name)
                    extractor.extract(symbol)
                except ValueError as e:
                    editor.error_message = str(e)
                    editor.error_visible = True
                    editor.error_buffer.text = f"\n  Invalid syntax in {meta.rel_path}:\n  {e}\n\n  Press [Enter] to dismiss."
                    event.app.layout.focus(editor.error_window)
                    event.app.invalidate()
                    return

            editor.result = text
            event.app.exit()

        asyncio.create_task(_do_save())

    @custom_bindings.add("c-q")
    def _quit(event) -> None:
        editor.result = None
        event.app.exit()

    return custom_bindings

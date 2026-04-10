import re
import sys
import os

from logger import log
from context import ProjectContext

try:
    from prompt_toolkit import Application
    from prompt_toolkit.application import get_app
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    from prompt_toolkit.key_binding.defaults import load_key_bindings
    from prompt_toolkit.layout.containers import (
        HSplit,
        VSplit,
        Window,
        FloatContainer,
        Float,
        ConditionalContainer,
    )
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.layout.menus import CompletionsMenu
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.styles import Style
    from prompt_toolkit.selection import SelectionState
    from prompt_toolkit.filters import Condition, has_selection, has_focus
    from prompt_toolkit.widgets import Frame
    from prompt_toolkit.lexers import Lexer
except ImportError:
    log.error(
        "'prompt_toolkit' library is missing. install it using: 'pip install prompt_toolkit'"
    )
    sys.exit(1)

try:
    import pygments
    from pygments.lexers.markup import MarkdownLexer
    from prompt_toolkit.lexers import PygmentsLexer, Lexer

    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False
    log.warning(
        "'pygments' library is missing. syntax highlighting will be disabled. install it using: 'pip install pygments'"
    )

try:
    from rapidfuzz import process, fuzz

    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    log.warning(
        "'rapidfuzz' library is missing. falling back to basic fuzzy search. install it using: 'pip install rapidfuzz'"
    )

if HAS_PYGMENTS:

    class CustomPromptLexer(Lexer):
        def __init__(self):
            self.md_lexer = PygmentsLexer(MarkdownLexer)
            self.pattern = re.compile(
                r"(\[@project\]|<@file:[^>]*>?|<@dir:[^>]*>?|<@type:[^>]*>?)"
            )

        def lex_document(self, document):
            get_original_line = self.md_lexer.lex_document(document)

            def get_line(lineno):
                original_tokens = get_original_line(lineno)
                text = document.lines[lineno]
                matches = list(self.pattern.finditer(text))

                if not matches:
                    return original_tokens

                new_tokens = []
                last_idx = 0
                for match in matches:
                    start, end = match.span()
                    if start > last_idx:
                        new_tokens.append(("", text[last_idx:start]))
                    new_tokens.append(("class:aicall", text[start:end]))
                    last_idx = end
                if last_idx < len(text):
                    new_tokens.append(("", text[last_idx:]))
                return new_tokens

            return get_line


class HelpLexer(Lexer):
    """Custom Lexer to highlight the Help Window text."""

    def __init__(self):
        self.pattern = re.compile(
            r"(<@[a-z]+:>|\[@project\]|\^\[.*?\]|\^[A-Za-z/_]+|\[.*?\]|< .*? >)"
        )

    def lex_document(self, document):
        def get_line(lineno):
            line = document.lines[lineno]
            tokens = []
            last_idx = 0
            for match in self.pattern.finditer(line):
                start, end = match.span()
                if start > last_idx:
                    tokens.append(("class:help-text", line[last_idx:start]))

                text = match.group(0)
                if text.startswith("<@") or text.startswith("[@"):
                    tokens.append(("class:aicall", text))
                elif (text.startswith("[ ") and text.endswith(" ]")) or (
                    text.startswith("< ") and text.endswith(" >")
                ):
                    tokens.append(("class:help-header", text))
                else:
                    tokens.append(("class:shortcut", text))
                last_idx = end

            if last_idx < len(line):
                tokens.append(("class:help-text", line[last_idx:]))
            return tokens

        return get_line


class MentionCompleter(Completer):
    def __init__(self, context: ProjectContext):
        self.context = context
        self.all_files = []
        self.all_dirs = set()
        self._build_cache()

    def _build_cache(self):
        """Pre-computes all allowed files and directories for fast fuzzy matching."""
        for file_path in self.context._get_allowed_files(self.context.target_dir):
            rel_path = str(file_path.relative_to(self.context.target_dir)).replace(
                "\\", "/"
            )
            self.all_files.append(rel_path)

            # Extract all parent directories
            parts = rel_path.split("/")[:-1]
            for i in range(len(parts)):
                self.all_dirs.add("/".join(parts[: i + 1]))

        self.all_dirs = sorted(list(self.all_dirs))

    def get_completions(self, document: Document, complete_event):
        text_before_cursor = document.text_before_cursor

        # Use[^><] to prevent unclosed tags from breaking the regex match
        match_path = re.search(r"<@(file|dir|type):([^><]*)$", text_before_cursor)
        if match_path:
            call_type = match_path.group(1)
            partial_val = match_path.group(2)

            candidates = []
            if call_type == "type":
                candidates = self.context.get_available_extensions()
            elif call_type == "file":
                candidates = self.all_files
            elif call_type == "dir":
                candidates = self.all_dirs

            if not partial_val:
                # Return top 15 alphabetically if no input
                for c in sorted(candidates)[:15]:
                    yield Completion(c + ">", start_position=0, display=c)
                return

            matched_items = []

            if HAS_RAPIDFUZZ:
                # Use RapidFuzz for high-performance fuzzy matching
                results = process.extract(partial_val, candidates, limit=15)
                # Filter out extremely poor matches, fallback to all if none are great
                matched_items = [res[0] for res in results if res[1] > 40]
                if not matched_items:
                    matched_items = [res[0] for res in results]
            else:
                # Fallback: Custom Substring & Subsequence Matcher
                matches = []
                lower_val = partial_val.lower().replace("\\", "/")

                for c in candidates:
                    lower_c = c.lower()
                    if lower_val in lower_c:
                        # Exact substring match gets a high score (shorter strings rank higher)
                        score = 100 - len(lower_c)
                        matches.append((c, score))
                    else:
                        # Subsequence match (e.g., "2md" matches "2.md")
                        it = iter(lower_c)
                        if all(char in it for char in lower_val):
                            score = 50 - len(lower_c)
                            matches.append((c, score))

                matches.sort(key=lambda x: x[1], reverse=True)
                matched_items = [m[0] for m in matches[:15]]

            for c in matched_items:
                yield Completion(c + ">", start_position=-len(partial_val), display=c)
            return

        # Match <@ for file/dir/type tag suggestions (preventing unclosed tags from breaking it)
        match_tag = re.search(r"<@([^><:]*)$", text_before_cursor)
        if match_tag:
            partial = match_tag.group(1)
            for tag in ["file:", "dir:", "type:"]:
                if tag.startswith(partial.lower()):
                    yield Completion(
                        tag, start_position=-len(partial), display=f"<@{tag}"
                    )
            return

        # Match[@ for project suggestion
        match_project = re.search(r"\[@([^\]\[]*)$", text_before_cursor)
        if match_project:
            partial = match_project.group(1)
            target = "project]"
            if target.startswith(partial.lower()):
                yield Completion(
                    target, start_position=-len(partial), display="[@project]"
                )
            return


@Condition
def has_completions_menu():
    b = get_app().current_buffer
    return b.complete_state is not None and len(b.complete_state.completions) > 0


@Condition
def is_completion_selected():
    b = get_app().current_buffer
    return (
        b.complete_state is not None and b.complete_state.current_completion is not None
    )


class InteractiveEditor:
    def __init__(
        self, initial_text: str, context: ProjectContext, show_help: bool = False
    ):
        self.context = context
        self.help_visible = show_help
        self.buffer = Buffer(
            document=Document(initial_text, cursor_position=0),
            completer=MentionCompleter(context),
            complete_while_typing=True,
        )
        self.result = None

    def run(self) -> str:
        default_bindings = load_key_bindings()
        custom_bindings = KeyBindings()

        # --- Help Window Setup ---
        help_text = """
[ autocomplete mentions ]

<@file:>   : attach file
<@dir:>    : attach folder
<@type:>   : attach file type
[@project] : attach project structure

[ navigation & editing ]

^S         : save and generate prompt
^Q         : quit without saving
^[Arrow]   : move cursor (wrap)
[Shift]    : select text
^C/X/V     : copy / cut / paste
^Z/Y       : undo / redo
^W         : delete previous word
^/         : toggle comment for current line/selection
^_         : same as[^/]

press [Enter], [F1] or [^G] to close help
        """.strip()

        self.help_buffer = Buffer(document=Document(help_text), read_only=True)

        # Use flexible Dimensions. It will prefer 65x24, but will safely shrink
        # down to 1x1 if the terminal is extremely small, preventing crashes.
        self.help_window = Window(
            content=BufferControl(
                buffer=self.help_buffer, lexer=HelpLexer()
            ),  # <-- Lexer applied
            style="class:help-text",
            wrap_lines=False,
            width=Dimension(preferred=65, max=100),
            height=Dimension(preferred=24, max=40),
        )

        lexer = CustomPromptLexer() if HAS_PYGMENTS else None
        self.main_window = Window(
            content=BufferControl(buffer=self.buffer, lexer=lexer)
        )

        editor_focus = has_focus(self.buffer)

        @Condition
        def is_help_visible():
            return self.help_visible

        def get_home_position(document):
            first_non_ws = document.get_start_of_line_position(after_whitespace=True)
            if first_non_ws == 0:
                return document.get_start_of_line_position(after_whitespace=False)
            return first_non_ws

        def _start_sel(b):
            if b.selection_state is None:
                b.selection_state = SelectionState(
                    original_cursor_position=b.cursor_position
                )

        # --- Help Window Toggles ---
        @custom_bindings.add("f1")
        @custom_bindings.add("c-g")
        def _toggle_help(event):
            self.help_visible = not self.help_visible
            if self.help_visible:
                event.app.layout.focus(self.help_window)
            else:
                event.app.layout.focus(self.main_window)

        @custom_bindings.add("escape", filter=is_help_visible)
        @custom_bindings.add("enter", filter=is_help_visible)
        def _close_help_esc(event):
            self.help_visible = False
            event.app.layout.focus(self.main_window)

        @custom_bindings.add(
            "enter",
            filter=editor_focus & has_completions_menu & ~is_completion_selected,
        )
        def _(event):
            b = event.current_buffer
            if b.complete_state and b.complete_state.completions:
                completion = b.complete_state.completions[0]
                b.apply_completion(completion)

        @custom_bindings.add(
            "enter", filter=editor_focus & has_completions_menu & is_completion_selected
        )
        def _(event):
            b = event.current_buffer
            if b.complete_state and b.complete_state.current_completion:
                b.apply_completion(b.complete_state.current_completion)

        @custom_bindings.add("escape", filter=editor_focus & has_completions_menu)
        def _(event):
            event.current_buffer.cancel_completion()

        @custom_bindings.add("c-a", filter=editor_focus)
        def _select_all(event):
            b = event.app.current_buffer
            b.selection_state = SelectionState(original_cursor_position=0)
            b.cursor_position = len(b.text)

        @custom_bindings.add("c-c", filter=editor_focus)
        def _copy(event):
            b = event.app.current_buffer
            if b.selection_state:
                data = b.copy_selection()
                event.app.clipboard.set_data(data)

        @custom_bindings.add("c-x", filter=editor_focus)
        def _cut(event):
            b = event.app.current_buffer
            if b.selection_state:
                data = b.cut_selection()
                event.app.clipboard.set_data(data)
                b.selection_state = None

        @custom_bindings.add("c-v", filter=editor_focus)
        def _paste(event):
            b = event.app.current_buffer
            if b.selection_state:
                b.cut_selection()
                b.selection_state = None
            b.paste_clipboard_data(event.app.clipboard.get_data())

        @custom_bindings.add("c-z", filter=editor_focus)
        def _undo(event):
            event.app.current_buffer.undo()

        @custom_bindings.add("c-y", filter=editor_focus)
        def _redo(event):
            event.app.current_buffer.redo()

        @custom_bindings.add("home", filter=editor_focus)
        def _home(event):
            b = event.current_buffer
            b.selection_state = None
            b.cursor_position += get_home_position(b.document)

        @custom_bindings.add("end", filter=editor_focus)
        def _end(event):
            b = event.current_buffer
            b.selection_state = None
            b.cursor_position += b.document.get_end_of_line_position()

        @custom_bindings.add("pageup", filter=editor_focus)
        def _pageup(event):
            b = event.current_buffer
            b.selection_state = None
            b.cursor_position += b.document.get_cursor_up_position(count=15)

        @custom_bindings.add("pagedown", filter=editor_focus)
        def _pagedown(event):
            b = event.current_buffer
            b.selection_state = None
            b.cursor_position += b.document.get_cursor_down_position(count=15)

        @custom_bindings.add("c-home", filter=editor_focus)
        def _c_home(event):
            b = event.current_buffer
            b.selection_state = None
            b.cursor_position = 0

        @custom_bindings.add("c-end", filter=editor_focus)
        def _c_end(event):
            b = event.current_buffer
            b.selection_state = None
            b.cursor_position = len(b.text)

        @custom_bindings.add("c-left", filter=editor_focus)
        def _c_left(event):
            b = event.current_buffer
            b.selection_state = None
            pos = b.document.find_previous_word_beginning()
            if pos is not None:
                b.cursor_position += pos
            else:
                b.cursor_position = 0

        @custom_bindings.add("c-right", filter=editor_focus)
        def _c_right(event):
            b = event.current_buffer
            b.selection_state = None
            pos = b.document.find_next_word_beginning()
            if pos is not None:
                b.cursor_position += pos
            else:
                b.cursor_position = len(b.text)

        @custom_bindings.add("s-home", filter=editor_focus)
        def _s_home(event):
            b = event.current_buffer
            _start_sel(b)
            b.cursor_position += get_home_position(b.document)

        @custom_bindings.add("s-end", filter=editor_focus)
        def _s_end(event):
            b = event.current_buffer
            _start_sel(b)
            b.cursor_position += b.document.get_end_of_line_position()

        @custom_bindings.add("s-pageup", filter=editor_focus)
        def _s_pageup(event):
            b = event.current_buffer
            _start_sel(b)
            b.cursor_position += b.document.get_cursor_up_position(count=15)

        @custom_bindings.add("s-pagedown", filter=editor_focus)
        def _s_pagedown(event):
            b = event.current_buffer
            _start_sel(b)
            b.cursor_position += b.document.get_cursor_down_position(count=15)

        @custom_bindings.add("s-c-home", filter=editor_focus)
        def _s_c_home(event):
            b = event.current_buffer
            _start_sel(b)
            b.cursor_position = 0

        @custom_bindings.add("s-c-end", filter=editor_focus)
        def _s_c_end(event):
            b = event.current_buffer
            _start_sel(b)
            b.cursor_position = len(b.text)

        @custom_bindings.add("s-c-left", filter=editor_focus)
        def _s_c_left(event):
            b = event.current_buffer
            _start_sel(b)
            pos = b.document.find_previous_word_beginning()
            if pos is not None:
                b.cursor_position += pos
            else:
                b.cursor_position = 0

        @custom_bindings.add("s-c-right", filter=editor_focus)
        def _s_c_right(event):
            b = event.current_buffer
            _start_sel(b)
            pos = b.document.find_next_word_beginning()
            if pos is not None:
                b.cursor_position += pos
            else:
                b.cursor_position = len(b.text)

        @custom_bindings.add("c-w", filter=editor_focus)
        def _c_w(event):
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
        def _c_delete(event):
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
        def _delete_selection(event):
            b = event.current_buffer
            b.cut_selection()
            b.selection_state = None

        @custom_bindings.add("<any>", filter=editor_focus & has_selection)
        def _type_over_selection(event):
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
        def _enter_over_selection(event):
            b = event.current_buffer
            b.cut_selection()
            b.selection_state = None
            b.insert_text("\n")

        @custom_bindings.add(
            "tab", filter=editor_focus & has_selection & ~has_completions_menu
        )
        def _tab_over_selection(event):
            b = event.current_buffer
            b.cut_selection()
            b.selection_state = None
            b.insert_text("    ")

        # --- Arrow Keys (Line Wrapping & Autocomplete Fix) ---
        @custom_bindings.add("left", filter=editor_focus & ~has_completions_menu)
        def _left(event):
            b = event.current_buffer
            b.selection_state = None
            if b.cursor_position > 0:
                b.cursor_position -= 1

        @custom_bindings.add("right", filter=editor_focus & ~has_completions_menu)
        def _right(event):
            b = event.current_buffer
            b.selection_state = None
            if b.cursor_position < len(b.text):
                b.cursor_position += 1

        @custom_bindings.add("s-left", filter=editor_focus & ~has_completions_menu)
        def _s_left(event):
            b = event.current_buffer
            _start_sel(b)
            if b.cursor_position > 0:
                b.cursor_position -= 1

        @custom_bindings.add("s-right", filter=editor_focus & ~has_completions_menu)
        def _s_right(event):
            b = event.current_buffer
            _start_sel(b)
            if b.cursor_position < len(b.text):
                b.cursor_position += 1

        @custom_bindings.add("up", filter=editor_focus & ~has_completions_menu)
        def _up(event):
            b = event.current_buffer
            b.selection_state = None
            b.cursor_position += b.document.get_cursor_up_position(count=1)

        @custom_bindings.add("down", filter=editor_focus & ~has_completions_menu)
        def _down(event):
            b = event.current_buffer
            b.selection_state = None
            b.cursor_position += b.document.get_cursor_down_position(count=1)

        # --- Context-Aware Commenting ---
        @custom_bindings.add(
            "c-_", filter=editor_focus
        )  # Terminals often send c-_ for Ctrl+/
        def _toggle_comment(event):
            b = event.current_buffer
            doc = b.document

            # 1. Detect language context by scanning upwards for code block fences
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

            COMMENT_SYNTAX = {
                "python": ("# ", ""),
                "py": ("# ", ""),
                "bash": ("# ", ""),
                "sh": ("# ", ""),
                "yaml": ("# ", ""),
                "yml": ("# ", ""),
                "ruby": ("# ", ""),
                "rb": ("# ", ""),
                "javascript": ("// ", ""),
                "js": ("// ", ""),
                "typescript": ("// ", ""),
                "ts": ("// ", ""),
                "java": ("// ", ""),
                "c": ("// ", ""),
                "cpp": ("// ", ""),
                "csharp": ("// ", ""),
                "cs": ("// ", ""),
                "go": ("// ", ""),
                "rust": ("// ", ""),
                "rs": ("// ", ""),
                "swift": ("// ", ""),
                "php": ("// ", ""),
                "html": ("<!-- ", " -->"),
                "xml": ("<!-- ", " -->"),
                "markdown": ("<!-- ", " -->"),
                "md": ("<!-- ", " -->"),
                "css": ("/* ", " */"),
                "sql": ("-- ", ""),
                "lua": ("-- ", ""),
            }

            if not in_block:
                prefix, suffix = ("<!-- ", " -->")
            else:
                prefix, suffix = COMMENT_SYNTAX.get(lang, ("# ", ""))

            # 2. Determine selection range
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

            # 3. Check if all target lines are already commented
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

            # 4. Apply toggle
            new_lines = list(lines)
            for i in range(start_row, end_row + 1):
                line = new_lines[i]
                s = line.lstrip()
                indent = line[: len(line) - len(s)]

                if not s and not all_commented:
                    continue

                if all_commented:
                    # Uncomment
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
                    # Comment
                    new_lines[i] = indent + prefix + s + suffix

            # 5. Restore cursor position safely
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
        def _save(event):
            self.result = self.buffer.text
            event.app.exit()

        @custom_bindings.add("c-q")
        def _quit(event):
            self.result = None
            event.app.exit()

        bindings = merge_key_bindings([default_bindings, custom_bindings])

        toolbar_text = (
            "[^G] help | [^S] save | [^Q] quit | <@file: / <@dir: / <@type: /[@project]"
        )
        bottom_toolbar = Window(
            content=FormattedTextControl(toolbar_text), height=1, style="class:toolbar"
        )

        body = HSplit([self.main_window, bottom_toolbar])

        help_frame = Frame(
            body=self.help_window,
            title="Help",
            style="class:help-frame",
        )

        # Use HSplit and VSplit with weight=1 spacers to perfectly center the frame
        help_overlay = ConditionalContainer(
            content=HSplit(
                [
                    Window(height=Dimension(weight=1)),  # Top spacer
                    VSplit(
                        [
                            Window(width=Dimension(weight=1)),  # Left spacer
                            help_frame,
                            Window(width=Dimension(weight=1)),  # Right spacer
                        ]
                    ),
                    Window(height=Dimension(weight=1)),  # Bottom spacer
                ]
            ),
            filter=is_help_visible,
        )

        layout = Layout(
            FloatContainer(
                content=body,
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        content=CompletionsMenu(max_height=12, scroll_offset=1),
                    ),
                    Float(
                        content=help_overlay,
                        top=0,
                        bottom=0,
                        left=0,
                        right=0,  # Fills the screen, allowing the inner splits to center the frame safely
                    ),
                ],
            )
        )

        style = Style.from_dict(
            {
                "toolbar": "bg:#333333 #ffffff",
                "completion-menu": "bg:#444444 #ffffff",
                "completion-menu.completion.current": "bg:#00aa00 #ffffff bold",
                "aicall": "fg:#00ffff bold",
                "help-frame": "bg:#222222 fg:#ffffff",
                "help-text": "bg:#222222 fg:#cccccc",
                "help-header": "fg:#00ff00 bold",  # Green bold for headers
                "shortcut": "fg:#ffff00 bold",  # Yellow bold for shortcuts
            }
        )

        app = Application(
            layout=layout,
            key_bindings=bindings,
            style=style,
            full_screen=True,
            mouse_support=True,
        )

        # Ensure Help window is focused immediately if opened on first run
        if self.help_visible:
            app.layout.focus(self.help_window)

        app.run()
        return self.result

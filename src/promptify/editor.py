import re
import sys
from typing import Iterable

from .logger import log
from .indexer import ProjectIndexer
from .bindings import setup_keybindings

try:
    from prompt_toolkit import Application
    from prompt_toolkit.completion import Completer, Completion, CompleteEvent
    from prompt_toolkit.key_binding.defaults import load_key_bindings
    from prompt_toolkit.key_binding import merge_key_bindings
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
    from prompt_toolkit.widgets import Frame
    from prompt_toolkit.lexers import Lexer
    from prompt_toolkit.filters import Condition
except ImportError:
    log.error(
        "'prompt_toolkit' library is missing. install it using: 'uv pip install prompt_toolkit'"
    )
    sys.exit(1)

try:
    import pygments  # NOQA: F401
    from pygments.lexers.markup import MarkdownLexer
    from prompt_toolkit.lexers import PygmentsLexer

    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False
    log.warning(
        "'pygments' library is missing. syntax highlighting will be disabled. install it using: 'uv pip install pygments'"
    )

try:
    from rapidfuzz import process, fuzz  # NOQA: F401
except ImportError:
    log.error(
        "'rapidfuzz' library is missing. install it using: 'uv pip install rapidfuzz'"
    )
    sys.exit(1)


if HAS_PYGMENTS:

    class CustomPromptLexer(Lexer):
        def __init__(self):
            self.md_lexer = PygmentsLexer(MarkdownLexer)
            self.pattern = re.compile(r"(\[@project\]|<@(file|dir|type|ext):[^>]*>?)")

        def lex_document(self, document: Document):
            get_original_line = self.md_lexer.lex_document(document)

            def get_line(lineno: int):
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

    def lex_document(self, document: Document):
        def get_line(lineno: int):
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
    """Provides ultra-fast autocomplete straight from the Watchdog-backed Index."""

    def __init__(self, indexer: ProjectIndexer):
        self.indexer = indexer

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text_before_cursor = document.text_before_cursor

        match_range = re.search(r"<@file:([^>:]+):([^><]*)$", text_before_cursor)
        if match_range:
            file_path = match_range.group(1)
            meta = self.indexer.files_by_rel.get(file_path)
            if meta:
                try:
                    with open(meta.path, "rb") as f:
                        lines = sum(1 for _ in f)
                    yield Completion(
                        "", start_position=0, display=f"[{lines} lines available]"
                    )
                except Exception:
                    pass
            return

        match_path = re.search(r"<@(file|dir|type|ext):([^><]*)$", text_before_cursor)
        if match_path:
            call_type = match_path.group(1)
            partial_val = match_path.group(2)

            if call_type in ("type", "ext"):
                parts = partial_val.split(",")
                current_val = parts[-1]
                candidates = self.indexer.get_all_extensions()

                matched_items = [
                    c for c in candidates if current_val.lower() in c.lower()
                ]
                for c in matched_items[:15]:
                    yield Completion(
                        c + ",", start_position=-len(current_val), display=c
                    )
                return

            candidates = []
            if call_type == "file":
                candidates = list(self.indexer.files_by_rel.keys())
            elif call_type == "dir":
                candidates = list(self.indexer.dirs)

            if not partial_val:
                for c in sorted(candidates)[:15]:
                    yield Completion(c + ">", start_position=0, display=c)
                return

            results = process.extract(partial_val, candidates, limit=15)
            matched_items = [res[0] for res in results if res[1] > 40]
            if not matched_items:
                matched_items = [res[0] for res in results]

            for c in matched_items:
                yield Completion(c + ">", start_position=-len(partial_val), display=c)
            return

        match_tag = re.search(r"<@([^><:]*)$", text_before_cursor)
        if match_tag:
            partial = match_tag.group(1)
            for tag in ["file:", "dir:", "ext:"]:
                if tag.startswith(partial.lower()):
                    yield Completion(
                        tag, start_position=-len(partial), display=f"<@{tag}"
                    )
            return

        match_project = re.search(r"\[@([^\]\[]*)$", text_before_cursor)
        if match_project:
            partial = match_project.group(1)
            target = "project]"
            if target.startswith(partial.lower()):
                yield Completion(
                    target, start_position=-len(partial), display="[@project]"
                )
            return


class InteractiveEditor:
    def __init__(
        self, initial_text: str, indexer: ProjectIndexer, show_help: bool = False
    ):
        self.help_visible = show_help
        self.buffer = Buffer(
            document=Document(initial_text, cursor_position=0),
            completer=MentionCompleter(indexer),
            complete_while_typing=True,
        )
        self.result: str | None = None

        help_text = """
[ autocomplete mentions ]

<@file:>   : attach file
<@dir:>    : attach folder
<@ext:>    : attach file extension
[@project] : attach project structure

[ navigation & editing ]

^[S]       : save and generate prompt
^[Q]       : quit without saving
^[Arrow]   : move cursor (wrap)
[Shift]    : select text
^[C/X/V]   : copy / cut / paste
^[Z/Y]     : undo / redo
^[W]       : delete previous word
^[/]       : toggle comment for current line/selection
^[_]       : same as [^/]

press [Enter], [F1] or ^[G] to close help
        """.strip()

        self.help_buffer = Buffer(document=Document(help_text), read_only=True)

        self.help_window = Window(
            content=BufferControl(buffer=self.help_buffer, lexer=HelpLexer()),
            style="class:help-text",
            wrap_lines=False,
            width=Dimension(preferred=65, max=100),
            height=Dimension(preferred=24, max=40),
        )

        lexer = CustomPromptLexer() if HAS_PYGMENTS else None
        self.main_window = Window(
            content=BufferControl(buffer=self.buffer, lexer=lexer)
        )

    async def run_async(self) -> str | None:
        default_bindings = load_key_bindings()
        custom_bindings = setup_keybindings(self)
        bindings = merge_key_bindings([default_bindings, custom_bindings])

        toolbar_text = (
            "[^G] help | [^S] save |[^Q] quit | <@file: / <@dir: / <@ext: / [@project]"
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

        help_overlay = ConditionalContainer(
            content=HSplit(
                [
                    Window(height=Dimension(weight=1)),
                    VSplit(
                        [
                            Window(width=Dimension(weight=1)),
                            help_frame,
                            Window(width=Dimension(weight=1)),
                        ]
                    ),
                    Window(height=Dimension(weight=1)),
                ]
            ),
            filter=Condition(lambda: self.help_visible),
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
                        right=0,
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
                "help-header": "fg:#00ff00 bold",
                "shortcut": "fg:#ffff00 bold",
            }
        )

        app = Application(
            layout=layout,
            key_bindings=bindings,
            style=style,
            full_screen=True,
            mouse_support=True,
        )

        if self.help_visible:
            app.layout.focus(self.help_window)

        await app.run_async()
        return self.result

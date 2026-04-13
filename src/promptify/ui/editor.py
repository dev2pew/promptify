import re
import sys
import asyncio
from typing import Iterable

from .logger import log
from ..core.indexer import ProjectIndexer
from ..core.resolver import PromptResolver
from ..core.mods import ModRegistry
from .bindings import setup_keybindings
from ..utils.i18n import strings

try:
    from prompt_toolkit import Application
    from prompt_toolkit.application.current import get_app
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
        WindowAlign,
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
    from prompt_toolkit.layout.processors import (
        HighlightMatchingBracketProcessor,
        Processor,
        Transformation,
    )
except ImportError:
    log.error(
        strings.get(
            "err_prompt_toolkit_missing",
            "'prompt_toolkit' library is missing. install it using: 'uv pip install prompt_toolkit'",
        )
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
        strings.get(
            "err_pygments_missing",
            "'pygments' library is missing. syntax highlighting will be disabled. install it using: 'uv pip install pygments'",
        )
    )

try:
    from rapidfuzz import process, fuzz  # NOQA: F401
except ImportError:
    log.error(
        strings.get(
            "err_rapidfuzz_missing",
            "'rapidfuzz' library is missing. install it using: 'uv pip install rapidfuzz'",
        )
    )
    sys.exit(1)


class HighlightTrailingWhitespaceProcessor(Processor):
    """Highlights trailing spaces and tabs at the end of each line."""

    def apply_transformation(self, transformation_input):
        fragments = transformation_input.fragments
        if not fragments:
            return Transformation(fragments)

        line_text = "".join(text for style, text in fragments)
        stripped = line_text.rstrip(" \t")

        if len(stripped) == len(line_text):
            return Transformation(fragments)

        new_fragments = []
        char_count = 0
        for style, text in fragments:
            if char_count >= len(stripped):
                new_fragments.append(("class:trailing-whitespace", text))
            elif char_count + len(text) > len(stripped):
                split_idx = len(stripped) - char_count
                new_fragments.append((style, text[:split_idx]))
                new_fragments.append(("class:trailing-whitespace", text[split_idx:]))
            else:
                new_fragments.append((style, text))
            char_count += len(text)

        return Transformation(new_fragments)


class EOFNewlineProcessor(Processor):
    def apply_transformation(self, transformation_input):
        document = transformation_input.document
        lineno = transformation_input.lineno
        tokens = transformation_input.fragments

        if lineno == document.line_count - 1:
            if document.text.endswith("\n") or not document.text:
                tokens = tokens + [("class:eof-newline", "¶")]
            else:
                tokens = tokens + [("class:eof-newline", "∅")]

        return Transformation(tokens)


if HAS_PYGMENTS:

    class CustomPromptLexer(Lexer):
        def __init__(self, registry: ModRegistry):
            self.md_lexer = PygmentsLexer(MarkdownLexer)
            self.registry = registry

        def lex_document(self, document: Document):
            get_original_line = self.md_lexer.lex_document(document)

            def get_line(lineno: int):
                original_tokens = get_original_line(lineno)
                text = document.lines[lineno]
                matches = list(self.registry.pattern.finditer(text))

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
    """Routes autocomplete generation requests through the dynamically registered Mods."""

    def __init__(self, indexer: ProjectIndexer, registry: ModRegistry):
        self.indexer = indexer
        self.registry = registry

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        # WRAP THE GENERATOR IN A LIST
        # THIS FORCES THE SCROLLBAR TO SEE THE FINAL COUNT IMMEDIATELY
        completions = list(
            self.registry.get_all_completions(document.text_before_cursor, self.indexer)
        )

        yield from completions


class InteractiveEditor:
    def __init__(
        self,
        initial_text: str,
        indexer: ProjectIndexer,
        resolver: PromptResolver,
        show_help: bool = False,
    ):
        self.help_visible = show_help
        self.indexer = indexer
        self.resolver = resolver
        self.token_count = 0

        self.buffer = Buffer(
            document=Document(initial_text, cursor_position=0),
            completer=MentionCompleter(indexer, resolver.registry),
            complete_while_typing=True,
        )
        self.result: str | None = None

        help_text = strings.get("help_text", "")
        self.help_buffer = Buffer(document=Document(help_text), read_only=True)

        self.help_window = Window(
            content=BufferControl(buffer=self.help_buffer, lexer=HelpLexer()),
            style="class:help-text",
            wrap_lines=False,
            width=Dimension(preferred=65, max=100),
            height=Dimension(preferred=24, max=40),
        )

        self.error_visible = False
        self.error_message = ""
        self.error_buffer = Buffer(document=Document(""), read_only=True)
        self.error_window = Window(
            content=BufferControl(buffer=self.error_buffer),
            style="class:error-text",
            wrap_lines=True,
            width=Dimension(preferred=60, max=80),
            height=Dimension(preferred=10, max=20),
        )

        lexer = CustomPromptLexer(resolver.registry) if HAS_PYGMENTS else None
        processors = [
            HighlightTrailingWhitespaceProcessor(),
            HighlightMatchingBracketProcessor(),
            EOFNewlineProcessor(),
        ]

        self.main_window = Window(
            content=BufferControl(
                buffer=self.buffer, lexer=lexer, input_processors=processors
            )
        )

    async def _update_tokens_loop(self):
        """Asynchronous, debounced task to compute resolution sizes without lagging the UI."""
        last_text = None
        last_count = 0
        while True:
            await asyncio.sleep(0.5)
            if self.result is not None:
                break

            current_text = self.buffer.text
            if current_text != last_text:
                last_text = current_text
                try:
                    resolved = await self.resolver.resolve_user(current_text)
                    new_count = len(resolved) // 4

                    # ONLY UPDATE STATE AND TRIGGER A REDRAW IF THE COUNT CHANGED
                    if new_count != last_count:
                        self.token_count = new_count
                        last_count = new_count
                        app = get_app()
                        if app:
                            app.invalidate()
                except Exception:
                    pass

    async def run_async(self) -> str | None:
        default_bindings = load_key_bindings()
        custom_bindings = setup_keybindings(self)
        bindings = merge_key_bindings([default_bindings, custom_bindings])

        top_bar = VSplit(
            [
                Window(width=Dimension(weight=1), style="class:topbar"),
                Window(
                    content=FormattedTextControl(" promptify editor "),
                    style="class:topbar-title",
                    align=WindowAlign.CENTER,
                ),
                Window(
                    content=FormattedTextControl(
                        lambda: f" ~{self.token_count} tokens "
                    ),
                    style="class:topbar-tokens",
                    align=WindowAlign.RIGHT,
                    width=Dimension(preferred=15),
                ),
            ],
            height=1,
            style="class:topbar",
        )

        toolbar_text = strings.get("toolbar_text", "")
        bottom_toolbar = VSplit(
            [
                Window(
                    content=FormattedTextControl(" " + toolbar_text + " "),
                    style="class:toolbar",
                ),
                Window(
                    content=FormattedTextControl(
                        lambda: (
                            f" :{self.buffer.document.cursor_position_row + 1}:{self.buffer.document.cursor_position_col + 1} "
                        )
                    ),
                    style="class:toolbar-right",
                    width=Dimension(preferred=15),
                    align=WindowAlign.RIGHT,
                ),
            ],
            height=1,
            style="class:toolbar",
        )

        body = HSplit([top_bar, self.main_window, bottom_toolbar])

        help_frame = Frame(
            body=self.help_window,
            title=strings.get("help_title", "Help"),
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

        error_frame = Frame(
            body=self.error_window,
            title=strings.get("error_title", "Error"),
            style="class:error-frame",
        )

        error_overlay = ConditionalContainer(
            content=HSplit(
                [
                    Window(height=Dimension(weight=1)),
                    VSplit(
                        [
                            Window(width=Dimension(weight=1)),
                            error_frame,
                            Window(width=Dimension(weight=1)),
                        ]
                    ),
                    Window(height=Dimension(weight=1)),
                ]
            ),
            filter=Condition(lambda: self.error_visible),
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
                    Float(
                        content=error_overlay,
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
                "topbar": "bg:#333333 #ffffff",
                "topbar-title": "bg:#333333 #00ffff bold",
                "topbar-tokens": "bg:#333333 #ffff00",
                "toolbar": "bg:#333333 #ffffff",
                "toolbar-right": "bg:#333333 #00ff00",
                "completion-menu": "bg:#444444 #ffffff",
                "completion-menu.completion.current": "bg:#00aa00 #ffffff bold",
                "aicall": "fg:#00ffff bold",
                "help-frame": "bg:#222222 fg:#ffffff",
                "help-text": "bg:#222222 fg:#cccccc",
                "help-header": "fg:#00ff00 bold",
                "shortcut": "fg:#ffff00 bold",
                "error-frame": "bg:#440000 fg:#ffffff",
                "error-text": "bg:#440000 fg:#ffaaaa",
                "trailing-whitespace": "bg:#ff0000",
                "eof-newline": "fg:#888888",
                "matching-bracket.cursor": "bg:#aaaaaa fg:#000000",
                "matching-bracket.other": "bg:#aaaaaa fg:#000000",
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

        token_task = asyncio.create_task(self._update_tokens_loop())
        await app.run_async()
        token_task.cancel()

        return self.result

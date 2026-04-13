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

    def tokenize_mention(text: str) -> list[tuple[str, str]]:
        """Granular tokenization for mentions, supporting semantic argument parsing."""
        if text == "[@project]":
            return [("class:mention-tag", "[@project]")]

        if not (text.startswith("<@") and text.endswith(">")):
            return [("class:mention-tag", text)]

        inner = text[2:-1]

        if ":" not in inner:
            return [("class:mention-tag", text)]

        tag_type, rest = inner.split(":", 1)
        tokens = [("class:mention-tag", f"<@{tag_type}")]

        def add_sep():
            tokens.append(("", ":"))

        # SEMANTIC PARSING BASED ON TAG TYPE
        if tag_type == "git":
            # STRUCTURE: <@GIT:CMD:PATH>
            if ":" in rest:
                cmd, path = rest.split(":", 1)
                add_sep()
                tokens.append(("class:mention-git-cmd", cmd))
                add_sep()
                tokens.append(("class:mention-path", path))
            else:
                add_sep()
                tokens.append(("class:mention-git-cmd", rest))

        elif tag_type in ("file", "symbol"):
            # STRUCTURE: <@TAG:PATH:ARG2>
            # USE RSPLIT IN CASE THE PATH CONTAINS COLONS (E.G., C:/...)
            if ":" in rest:
                path, arg2 = rest.rsplit(":", 1)
                add_sep()
                tokens.append(("class:mention-path", path))
                add_sep()

                if tag_type == "symbol":
                    if "." in arg2:
                        cls, dot, method = arg2.partition(".")
                        tokens.append(("class:mention-class", cls))
                        tokens.append(("", dot))
                        tokens.append(("class:mention-method", method))
                    elif arg2 and arg2[0].isupper():
                        tokens.append(("class:mention-class", arg2))
                    else:
                        tokens.append(("class:mention-function", arg2))
                else:  # FILE
                    tokens.append(("class:mention-range", arg2))
            else:
                add_sep()
                tokens.append(("class:mention-path", rest))

        elif tag_type == "ext":
            # STRUCTURE: <@EXT:LIST>
            add_sep()
            tokens.append(("class:mention-ext", rest))

        else:
            # STRUCTURE: <@DIR:PATH> OR <@TREE:PATH>
            add_sep()
            tokens.append(("class:mention-path", rest))

        tokens.append(("class:mention-tag", ">"))
        return tokens

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

                # FLATTEN ORIGINAL PYGMENTS TOKENS TO A CHARACTER MAP
                chars = []
                for style, chars_str in original_tokens:
                    for c in chars_str:
                        chars.append((style, c))

                new_tokens = []
                last_idx = 0

                for m in matches:
                    start, end = m.span()

                    # 1. RECOVER ORIGINAL MARKDOWN TOKENS BEFORE THE MATCH
                    curr_style = None
                    curr_text = []
                    for i in range(last_idx, start):
                        st, c = chars[i]
                        if st != curr_style:
                            if curr_text:
                                new_tokens.append((curr_style, "".join(curr_text)))
                            curr_style = st
                            curr_text = [c]
                        else:
                            curr_text.append(c)
                    if curr_text:
                        new_tokens.append((curr_style, "".join(curr_text)))

                    # 2. INJECT GRANULAR MENTION TOKENS
                    new_tokens.extend(tokenize_mention(m.group(0)))
                    last_idx = end

                # 3. RECOVER ORIGINAL MARKDOWN TOKENS AFTER THE LAST MATCH
                curr_style = None
                curr_text = []
                for i in range(last_idx, len(chars)):
                    st, c = chars[i]
                    if st != curr_style:
                        if curr_text:
                            new_tokens.append((curr_style, "".join(curr_text)))
                        curr_style = st
                        curr_text = [c]
                    else:
                        curr_text.append(c)
                if curr_text:
                    new_tokens.append((curr_style, "".join(curr_text)))

                return new_tokens

            return get_line


class HelpLexer(Lexer):
    """Robust regex-based lexer for the Help window text."""

    def __init__(self):
        # 1. HEADERS: [ GENERAL ]
        self.header_re = re.compile(r"^\s*\[ .* \]\s*$")
        # 2. MENTIONS OR KEYS: <@...> | [@PROJECT] | ^[X]
        self.combined_re = re.compile(r"(<@[^>]+>|\[@project\])|(\^?\[[^\]]+\])")

    def lex_document(self, document: Document):
        def get_line(lineno: int):
            text = document.lines[lineno]

            if self.header_re.match(text):
                return [("class:help-header", text)]

            tokens = []
            last_idx = 0

            for match in self.combined_re.finditer(text):
                start = match.start()
                if start > last_idx:
                    tokens.append(("", text[last_idx:start]))

                mention, key = match.groups()
                if mention:
                    # INJECT OUR GRANULAR TOKENS!
                    tokens.extend(tokenize_mention(mention))
                else:
                    # KEYS LIKE ^[S]
                    tokens.append(("class:help-key", key))

                last_idx = match.end()

            if last_idx < len(text):
                tokens.append(("", text[last_idx:]))

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
                    new_count = len(resolved) // 3.2

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
                    content=FormattedTextControl(" < promptify editor > "),
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
            title=" < " + strings.get("help_title", "help") + " > ",
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
            title=" < " + strings.get("error_title", "error") + " > ",
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
                # UI LAYOUT
                "topbar": "bg:#333333 #ffffff",
                "topbar-title": "bg:#333333 #00ffff bold",
                "topbar-tokens": "bg:#333333 #ffff00",
                "toolbar": "bg:#333333 #ffffff",
                "toolbar-right": "bg:#333333 #00ff00",
                "completion-menu": "bg:#444444 #ffffff",
                "completion-menu.completion.current": "bg:#00aa00 #ffffff bold",
                # GRANULAR MENTION STYLES
                "mention-tag": "fg:#00ffff bold",  # CYAN: <@FILE, >, [@PROJECT]
                "mention-path": "fg:#ffaa00",  # ORANGE: SRC/MAIN.PY
                "mention-range": "fg:#ff55ff",  # MAGENTA/PINK: 12-20
                "mention-ext": "fg:#ffaa00",  # ORANGE: MD,PY
                "mention-git-cmd": "fg:#00aa00",  # GREEN: DIFF, STATUS
                "mention-class": "fg:#00ff00 bold",  # BRIGHT GREEN: MYCLASS
                "mention-function": "fg:#5555ff",  # BLUE: MY_FUNC
                "mention-method": "fg:#55ffff",  # LIGHT CYAN: METHOD
                # HELP MENU OVERRIDES
                "help-header": "fg:#00ff00 bold",  # GREEN SECTION HEADERS
                "help-key": "fg:#ffff00",  # YELLOW NAVIGATION KEYS
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

import re
import sys
from typing import Iterable

from .logger import log
from .indexer import ProjectIndexer
from .bindings import setup_keybindings
from .i18n import strings
from .models import FileMeta

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
    from prompt_toolkit.layout.processors import (
        HighlightMatchingBracketProcessor,
        Processor,
        Transformation,
    )
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
        def __init__(self):
            self.md_lexer = PygmentsLexer(MarkdownLexer)
            self.pattern = re.compile(
                r"(\[@project\]|<@(file|dir|type|ext|git|symbol):[^>]*>?)"
            )

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
        self._symbol_cache: dict[str, tuple[float, list[str]]] = {}

    def _get_symbols_for_file(self, meta: FileMeta) -> list[str]:
        cached = self._symbol_cache.get(meta.rel_path)
        if cached and cached[0] == meta.mtime:
            return cached[1]

        try:
            with open(meta.path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            from .extractor import SymbolExtractor

            extractor = SymbolExtractor(content, meta.path.name)
            symbols = list(extractor.symbols.keys())
            self._symbol_cache[meta.rel_path] = (meta.mtime, symbols)
            return symbols
        except Exception:
            return []

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

        match_git_diff = re.search(r"<@git:diff:([^><]*)$", text_before_cursor)
        if match_git_diff:
            partial_val = match_git_diff.group(1)
            candidates = list(self.indexer.files_by_rel.keys()) + list(
                self.indexer.dirs
            )
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

        match_path = re.search(
            r"<@(file|dir|type|ext|symbol):([^><]*)$", text_before_cursor
        )
        if match_path:
            call_type = match_path.group(1)
            partial_val = match_path.group(2)

            if call_type == "symbol":
                parts = partial_val.split(":", 1)
                if len(parts) == 1:
                    candidates = list(self.indexer.files_by_rel.keys())
                    if not parts[0]:
                        for c in sorted(candidates)[:15]:
                            yield Completion(c + ":", start_position=0, display=c)
                        return
                    results = process.extract(parts[0], candidates, limit=15)
                    matched_items = [res[0] for res in results if res[1] > 40] or [
                        res[0] for res in results
                    ]
                    for c in matched_items:
                        yield Completion(
                            c + ":", start_position=-len(parts[0]), display=c
                        )
                    return
                elif len(parts) == 2:
                    file_path = parts[0]
                    symbol_partial = parts[1]
                    if file_path in self.indexer.files_by_rel:
                        meta = self.indexer.files_by_rel[file_path]
                        symbols = self._get_symbols_for_file(meta)
                        if not symbol_partial:
                            for s in sorted(symbols)[:15]:
                                yield Completion(s + ">", start_position=0, display=s)
                            return
                        results = process.extract(symbol_partial, symbols, limit=15)
                        matched_items = [res[0] for res in results if res[1] > 40] or [
                            res[0] for res in results
                        ]
                        for s in matched_items:
                            yield Completion(
                                s + ">", start_position=-len(symbol_partial), display=s
                            )
                    return

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

        match_git = re.search(r"<@git:([^><:]*)$", text_before_cursor)
        if match_git:
            partial = match_git.group(1)
            for c in ["diff>", "status>", "diff:"]:
                if c.startswith(partial.lower()):
                    yield Completion(c, start_position=-len(partial), display=c)
            return

        match_tag = re.search(r"<@([^><:]*)$", text_before_cursor)
        if match_tag:
            partial = match_tag.group(1)
            for tag in ["file:", "dir:", "ext:", "git:", "symbol:"]:
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
        self.indexer = indexer
        self.buffer = Buffer(
            document=Document(initial_text, cursor_position=0),
            completer=MentionCompleter(indexer),
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

        lexer = CustomPromptLexer() if HAS_PYGMENTS else None

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

    async def run_async(self) -> str | None:
        default_bindings = load_key_bindings()
        custom_bindings = setup_keybindings(self)
        bindings = merge_key_bindings([default_bindings, custom_bindings])

        toolbar_text = strings.get("toolbar_text", "")
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

        error_frame = Frame(
            body=self.error_window,
            title="Error",
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
                "toolbar": "bg:#333333 #ffffff",
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

        await app.run_async()
        return self.result

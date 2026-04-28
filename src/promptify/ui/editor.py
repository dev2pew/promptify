"""
CLI TERMINAL TEXT EDITOR DRIVEN BY PROMPT-TOOLKIT AND PYGMENTS.
IMPLEMENTS HIGHLIGHTING, AUTOCOMPLETION, INVALID MENTION MARKING, AND SEARCH.
"""

import re
import sys
import asyncio
from typing import Callable, Iterable, cast

from .logger import log
from ..core.indexer import ProjectIndexer
from ..core.resolver import PromptResolver
from ..core.mods import ModRegistry, split_file_query_and_range
from .bindings import setup_keybindings
from ..utils.i18n import get_string

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
    from prompt_toolkit.layout.controls import (
        BufferControl,
        FormattedTextControl,
        UIContent,
    )
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.layout.margins import ScrollbarMargin
    from prompt_toolkit.data_structures import Point
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import Frame, SearchToolbar
    from prompt_toolkit.lexers import Lexer
    from prompt_toolkit.filters import (
        Condition,
        FilterOrBool,
        has_completions,
        is_done,
        to_filter,
    )
    from prompt_toolkit.layout.processors import (
        HighlightMatchingBracketProcessor,
        Processor,
        Transformation,
    )
    from prompt_toolkit.layout.containers import ScrollOffsets
    from prompt_toolkit.layout.menus import (
        CompletionsMenuControl,
        _get_menu_item_fragments,
    )
except ImportError:
    log.error(
        get_string(
            "err_prompt_toolkit_missing",
            "'prompt_toolkit' library is missing. install it using: 'uv pip install prompt_toolkit'",
        )
    )
    sys.exit(1)


def _fragment_text(fragment: tuple[object, ...]) -> str:
    """READS PROMPT-TOOLKIT FRAGMENTS THAT MAY OPTIONALLY CARRY A THIRD FIELD."""
    if len(fragment) < 2 or not isinstance(fragment[1], str):
        return ""
    return fragment[1]


try:
    import pygments  # NOQA: F401
    from pygments.lexers.markup import MarkdownLexer
    from prompt_toolkit.lexers import PygmentsLexer

    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False
    log.warning(
        get_string(
            "err_pygments_missing",
            "'pygments' library is missing. syntax highlighting will be disabled. install it using: 'uv pip install pygments'",
        )
    )

try:
    from rapidfuzz import process, fuzz  # NOQA: F401
except ImportError:
    log.error(
        get_string(
            "err_rapidfuzz_missing",
            "'rapidfuzz' library is missing. install it using: 'uv pip install rapidfuzz'",
        )
    )
    sys.exit(1)


class HighlightTrailingWhitespaceProcessor(Processor):
    """HIGHLIGHTS TRAILING SPACES AND TABS AT THE END OF EACH LINE."""

    def apply_transformation(self, transformation_input):
        fragments = transformation_input.fragments
        if not fragments:
            return Transformation(fragments)

        line_text = "".join(_fragment_text(fragment) for fragment in fragments)
        stripped = line_text.rstrip(" \t")

        if len(stripped) == len(line_text):
            return Transformation(fragments)

        new_fragments = []
        char_count = 0
        for fragment in fragments:
            style = cast(str, fragment[0])
            text = _fragment_text(fragment)
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
    """INDICATES MISSING EOF NEWLINE VISUALLY."""

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
        """GRANULAR TOKENIZATION FOR MENTIONS, SUPPORTING SEMANTIC ARGUMENT PARSING."""
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
        elif tag_type in ("file", "symbol", "tree"):
            # STRUCTURE: <@TAG:PATH:ARG2>
            # USE REGEX TO SAFELY SPLIT PATH AND OPTIONAL ARGUMENT, RESPECTING WINDOWS PATHS (E.G., C:/...)
            m = re.match(r"^([^>]+?)(?::([^>:]+))?$", rest)
            if m:
                path, arg2 = m.groups()
                add_sep()
                tokens.append(("class:mention-path", path))
                if arg2:
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
                    elif tag_type == "tree":
                        tokens.append(("class:mention-depth", arg2))
                    else:  # FILE
                        tokens.append(("class:mention-range", arg2))
            else:
                add_sep()
                tokens.append(("class:mention-path", rest))

        elif tag_type in ("ext", "type"):
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
        """CUSTOM LEXER TO EMBED TAG HIGHLIGHTING AND INVALID MENTION DETECTION NATIVELY."""

        def __init__(
            self,
            registry: ModRegistry,
            indexer: ProjectIndexer,
            resolver: PromptResolver,
            expensive_checks_enabled: Callable[[], bool] | None = None,
        ):
            self.md_lexer = PygmentsLexer(MarkdownLexer)
            self.registry = registry
            self.indexer = indexer
            self.resolver = resolver
            self.expensive_checks_enabled = expensive_checks_enabled or (lambda: True)
            self.mention_pattern = re.compile(r"<@[^>\n]+(?:>|$)|\[@project\]")
            self._validation_cache: dict[tuple[int, str], bool] = {}

        def is_valid_mention(self, text: str) -> bool:
            """VALIDATES THE INTEGRITY OF A MENTION AND ITS EXISTENCE IN THE INDEXER."""
            cache_key = (self.indexer.revision, text)
            cached = self._validation_cache.get(cache_key)
            if cached is not None:
                return cached

            if text == "[@project]":
                self._validation_cache[cache_key] = True
                return True
            if not text.endswith(">"):
                self._validation_cache[cache_key] = False
                return False

            pattern = self.registry.pattern
            if pattern is None:
                self.registry.build()
                pattern = self.registry.pattern
            if pattern is None:
                self._validation_cache[cache_key] = False
                return False

            match = pattern.fullmatch(text)
            if not match:
                self._validation_cache[cache_key] = False
                return False

            try:
                mod, _ = self.registry.get_mod_and_text(match)

                if mod.name == "mod_file":
                    body = text.removeprefix("<@file:").removesuffix(">")
                    path, _ = split_file_query_and_range(body)
                    if not self.resolver.context.is_safe_query_path(
                        path
                    ) or not self.indexer.find_matches(path):
                        self._validation_cache[cache_key] = False
                        return False
                elif mod.name in ("mod_dir", "mod_tree"):
                    p = re.match(r"<@(dir|tree):([^>:]+)", text)
                    if p:
                        clean = p.group(2).replace("\\", "/").strip("/")
                        if clean == "":
                            self._validation_cache[cache_key] = True
                            return True
                        if not self.resolver.context.is_safe_query_path(clean):
                            self._validation_cache[cache_key] = False
                            return False
                        if (
                            clean
                            and clean not in self.indexer.dirs
                            and not any(d.startswith(clean) for d in self.indexer.dirs)
                        ):
                            self._validation_cache[cache_key] = False
                            return False
                elif mod.name == "mod_symbol":
                    p = re.match(r"<@symbol:([^>:]+?)(?::([^>]+))?>", text)
                    if not p:
                        self._validation_cache[cache_key] = False
                        return False
                    path = p.group(1)
                    if not self.resolver.context.is_safe_query_path(path):
                        self._validation_cache[cache_key] = False
                        return False
                    if not self.indexer.find_matches(path):
                        self._validation_cache[cache_key] = False
                        return False
                elif mod.name == "mod_ext":
                    p = re.match(r"<@(type|ext):([^>]+)>", text)
                    if not p:
                        self._validation_cache[cache_key] = False
                        return False
                    exts = [e.strip().lower() for e in p.group(2).split(",")]
                    if not self.indexer.get_by_extensions(exts):
                        self._validation_cache[cache_key] = False
                        return False
                self._validation_cache[cache_key] = True
                return True
            except Exception:
                self._validation_cache[cache_key] = False
                return False

        def lex_document(self, document: Document):
            get_original_line = self.md_lexer.lex_document(document)

            def get_line(lineno: int):
                original_tokens = get_original_line(lineno)
                text = document.lines[lineno]
                matches = list(self.mention_pattern.finditer(text))

                if not matches:
                    return original_tokens

                # FLATTEN ORIGINAL PYGMENTS TOKENS TO A CHARACTER MAP
                chars = []
                for fragment in original_tokens:
                    style = cast(str, fragment[0])
                    chars_str = _fragment_text(fragment)
                    for c in chars_str:
                        chars.append((style, c))

                new_tokens = []
                last_idx = 0

                for m in matches:
                    start, end = m.span()
                    m_text = m.group(0)

                    # RECOVER ORIGINAL MARKDOWN TOKENS BEFORE THE MATCH
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

                    # INJECT GRANULAR MENTION TOKENS OR INVALID STYLING
                    if not self.expensive_checks_enabled():
                        new_tokens.extend(tokenize_mention(m_text))
                    elif not self.is_valid_mention(m_text):
                        new_tokens.append(("class:invalid-syntax", m_text))
                    else:
                        new_tokens.extend(tokenize_mention(m_text))

                    last_idx = end

                # RECOVER ORIGINAL MARKDOWN TOKENS AFTER THE LAST MATCH
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
    """ROBUST REGEX-BASED LEXER FOR THE HELP WINDOW TEXT."""

    def __init__(self):

        # HEADERS: [ GENERAL ]
        self.header_re = re.compile(r"^\s*\[ .* \]\s*$")

        # MENTIONS OR KEYS: <@...> | [@PROJECT] | ^[X]
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
    """ROUTES AUTOCOMPLETE GENERATION REQUESTS THROUGH THE DYNAMICALLY REGISTERED MODS."""

    def __init__(
        self,
        indexer: ProjectIndexer,
        registry: ModRegistry,
        should_complete: Callable[[Document], bool],
    ):
        self.indexer = indexer
        self.registry = registry
        self.should_complete = should_complete

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        if not self.should_complete(document):
            return

        # WRAP THE GENERATOR IN A LIST
        # THIS FORCES THE SCROLLBAR TO SEE THE FINAL COUNT IMMEDIATELY
        completions = list(
            self.registry.get_all_completions(document.text_before_cursor, self.indexer)
        )
        yield from completions


class ResponsiveCompletionsMenuControl(CompletionsMenuControl):
    """COMPLETION MENU CONTROL THAT RESPECTS THE ACTIVE VIEWPORT WIDTH."""

    MIN_META_COLUMN_WIDTH = 12
    MIN_WIDTH_FOR_META = 28

    def preferred_width(self, max_available_width: int) -> int | None:
        complete_state = get_app().current_buffer.complete_state
        if not complete_state:
            return 0

        menu_width = self._get_menu_width(max_available_width, complete_state)
        menu_meta_width = self._get_menu_meta_width(
            max(0, max_available_width - menu_width), complete_state
        )
        preferred = menu_width + menu_meta_width
        return min(max_available_width, preferred)

    def _get_column_widths(self, width: int, complete_state) -> tuple[int, int, bool]:
        """SPLITS AVAILABLE WIDTH BETWEEN THE LABEL AND THE PATH META COLUMN."""
        menu_width = self._get_menu_width(width, complete_state)
        meta_width = self._get_menu_meta_width(
            max(0, width - menu_width), complete_state
        )
        show_meta = self._show_meta(complete_state)

        if not show_meta or width < self.MIN_WIDTH_FOR_META:
            return min(width, menu_width), 0, False

        reserved_meta = min(
            meta_width or self.MIN_META_COLUMN_WIDTH,
            max(0, width - self.MIN_WIDTH),
        )
        reserved_meta = max(self.MIN_META_COLUMN_WIDTH, reserved_meta)
        menu_width = min(menu_width, max(self.MIN_WIDTH, width - reserved_meta))
        meta_width = min(meta_width, max(0, width - menu_width))

        if meta_width < self.MIN_META_COLUMN_WIDTH:
            return min(width, menu_width), 0, False

        return menu_width, meta_width, True

    def create_content(self, width: int, height: int) -> UIContent:
        """RENDERS COMPLETIONS USING A VIEWPORT-AWARE LABEL/META SPLIT."""
        complete_state = get_app().current_buffer.complete_state
        if not complete_state:
            return UIContent()

        completions = complete_state.completions
        index = complete_state.complete_index
        menu_width, meta_width, show_meta = self._get_column_widths(
            width, complete_state
        )

        def get_line(i: int):
            completion = completions[i]
            is_current_completion = i == index
            result = _get_menu_item_fragments(
                completion, is_current_completion, menu_width, space_after=show_meta
            )

            if show_meta:
                result += self._get_menu_item_meta_fragments(
                    completion, is_current_completion, meta_width
                )
            return result

        return UIContent(
            get_line=get_line,
            cursor_position=Point(x=0, y=index or 0),
            line_count=len(completions),
        )


class ResponsiveCompletionsMenu(ConditionalContainer):
    """DROPDOWN MENU THAT TRACKS THE TERMINAL SIZE INSTEAD OF A FIXED WIDTH HINT."""

    def __init__(
        self,
        max_height: int | None = None,
        scroll_offset: int | Callable[[], int] = 0,
        extra_filter: FilterOrBool = True,
        display_arrows: FilterOrBool = False,
        z_index: int = 10**8,
    ) -> None:
        extra_filter_filter = to_filter(extra_filter)
        display_arrows_filter = to_filter(display_arrows)

        super().__init__(
            content=Window(
                content=ResponsiveCompletionsMenuControl(),
                width=Dimension(min=8),
                height=Dimension(min=1, max=max_height),
                scroll_offsets=ScrollOffsets(top=scroll_offset, bottom=scroll_offset),
                right_margins=[ScrollbarMargin(display_arrows=display_arrows_filter)],
                dont_extend_width=True,
                style="class:completion-menu",
                z_index=z_index,
            ),
            filter=extra_filter_filter & has_completions & ~is_done,
        )


class InteractiveEditor:
    """MANAGES THE CORE PROMPT-TOOLKIT TERMINAL EDITOR."""

    BULK_EDIT_SUSPEND_SECONDS = 0.35
    BULK_EDIT_SIZE_THRESHOLD = 2048
    COMPLETION_MENU_MAX_HEIGHT = 12

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
        self._bulk_mode_until = 0.0

        self.buffer = Buffer(
            document=Document(initial_text, cursor_position=0),
            completer=MentionCompleter(
                cast(ProjectIndexer, indexer),
                cast(ModRegistry, resolver.registry),
                self.should_complete,
            ),
            complete_while_typing=Condition(self.should_complete_while_typing),
        )
        self.result: str | None = None

        help_text = get_string("help_text", "")
        self.help_buffer = Buffer(document=Document(help_text), read_only=True)

        self.help_window = Window(
            content=BufferControl(buffer=self.help_buffer, lexer=HelpLexer()),
            style="class:help-text",
            wrap_lines=False,
            width=Dimension(min=40, max=160, weight=1),
            height=Dimension(min=12, max=40, weight=1),
        )

        self.error_visible = False
        self.error_message = ""
        self.error_buffer = Buffer(document=Document(""), read_only=True)
        self.error_window = Window(
            content=BufferControl(buffer=self.error_buffer),
            style="class:error-text",
            wrap_lines=True,
            width=Dimension(min=36, max=120, weight=1),
            height=Dimension(min=8, max=24, weight=1),
        )

        self.search_toolbar = SearchToolbar()

        lexer = (
            CustomPromptLexer(
                cast(ModRegistry, resolver.registry),
                cast(ProjectIndexer, indexer),
                resolver,
                self.expensive_checks_enabled,
            )
            if HAS_PYGMENTS
            else None
        )
        processors = [
            HighlightTrailingWhitespaceProcessor(),
            HighlightMatchingBracketProcessor(),
            EOFNewlineProcessor(),
        ]

        self.main_window = Window(
            content=BufferControl(
                buffer=self.buffer,
                lexer=lexer,
                input_processors=processors,
                search_buffer_control=self.search_toolbar.control,
            )
        )
        self.completions_menu = ResponsiveCompletionsMenu(
            max_height=self.COMPLETION_MENU_MAX_HEIGHT,
            scroll_offset=1,
        )

    def _build_centered_overlay(
        self, container, visible_filter: Condition
    ) -> ConditionalContainer:
        """CENTERS AN INTERACTIVE PANEL WHILE ALLOWING IT TO SCALE WITH THE VIEWPORT."""
        return ConditionalContainer(
            content=HSplit(
                [
                    Window(height=Dimension(weight=1)),
                    VSplit(
                        [
                            Window(width=Dimension(weight=1)),
                            container,
                            Window(width=Dimension(weight=1)),
                        ],
                        padding=0,
                    ),
                    Window(height=Dimension(weight=1)),
                ],
                padding=0,
            ),
            filter=visible_filter,
        )

    async def _update_tokens_loop(self):
        """ASYNCHRONOUS, DEBOUNCED TASK UTILIZING FAST PROXY METRICS FOR TOKEN SIZE."""
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
                    new_count = await self.resolver.estimate_tokens(current_text)

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
        """EXECUTES THE FULL SCREEN EDITOR."""
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

        toolbar_text = get_string("toolbar_text", "")
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

        body = HSplit([top_bar, self.main_window, self.search_toolbar, bottom_toolbar])

        help_frame = Frame(
            body=self.help_window,
            title=" < " + get_string("help_title", "help") + " > ",
            style="class:help-frame",
        )

        help_overlay = self._build_centered_overlay(
            help_frame, Condition(lambda: self.help_visible)
        )

        error_frame = Frame(
            body=self.error_window,
            title=" < " + get_string("error_title", "error") + " > ",
            style="class:error-frame",
        )

        error_overlay = self._build_centered_overlay(
            error_frame, Condition(lambda: self.error_visible)
        )

        layout = Layout(
            FloatContainer(
                content=body,
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        content=self.completions_menu,
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
                "mention-depth": "fg:#ff55ff",
                "mention-ext": "fg:#ffaa00",  # ORANGE: MD,PY
                "mention-git-cmd": "fg:#00aa00",  # GREEN: DIFF, STATUS
                "mention-class": "fg:#00ff00 bold",  # BRIGHT GREEN: MYCLASS
                "mention-function": "fg:#5555ff",  # BLUE: MY_FUNC
                "mention-method": "fg:#55ffff",  # LIGHT CYAN: METHOD
                # INVALID SYNTAX OVERRIDE (RED BG, WHITE FG)
                "invalid-syntax": "bg:#ff0000 fg:#ffffff",
                # HELP MENU OVERRIDES
                "help-header": "fg:#00ff00 bold",  # GREEN SECTION HEADERS
                "help-key": "fg:#ffff00",  # YELLOW NAVIGATION KEYS
                # ENHANCED VISIBILITY
                "trailing-whitespace": "bg:#ff0000",
                "eof-newline": "fg:#ff0000",
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

    def expensive_checks_enabled(self) -> bool:
        """SKIPS REDRAW-TIME VALIDATION WHILE A BULK EDIT IS STILL SETTLING."""
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            return True
        return now >= self._bulk_mode_until

    def should_complete_while_typing(self) -> bool:
        """ONLY RUNS FUZZY COMPLETION WHEN THE CURSOR IS INSIDE AN ACTIVE MENTION."""
        if not self.expensive_checks_enabled():
            return False
        return self.should_complete(self.buffer.document)

    def should_complete(self, document: Document) -> bool:
        """GATES AUTOCOMPLETE SO PASTES AND NORMAL PROSE DO NOT TRIGGER FUZZY SEARCH."""
        tail = document.text_before_cursor[-256:]
        return bool(re.search(r"(<@[^>\n]*)|(\[@[^\]\n]*)$", tail))

    def start_bulk_edit(self, inserted_text: str) -> None:
        """TEMPORARILY RELAXES COMPLETION AND VALIDATION AFTER LARGE PASTES."""
        if len(inserted_text) < self.BULK_EDIT_SIZE_THRESHOLD:
            return

        loop = asyncio.get_running_loop()
        self._bulk_mode_until = max(
            self._bulk_mode_until, loop.time() + self.BULK_EDIT_SUSPEND_SECONDS
        )

        async def _refresh_after_pause():
            await asyncio.sleep(self.BULK_EDIT_SUSPEND_SECONDS)
            try:
                app = get_app()
            except Exception:
                return
            app.invalidate()

        asyncio.create_task(_refresh_after_pause())

    def paste_text(self, buffer: Buffer, text: str) -> None:
        """APPLIES PASTED TEXT THROUGH THE FAST BULK-EDIT PATH."""
        if not text:
            return

        buffer.save_to_undo_stack()

        if buffer.selection_state:
            buffer.cut_selection()
            buffer.selection_state = None

        self.start_bulk_edit(text)
        buffer.insert_text(text)

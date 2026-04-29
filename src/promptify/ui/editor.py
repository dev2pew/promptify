"""
CLI TERMINAL TEXT EDITOR DRIVEN BY PROMPT-TOOLKIT AND PYGMENTS.
IMPLEMENTS HIGHLIGHTING, AUTOCOMPLETION, INVALID MENTION MARKING, AND SEARCH.
"""

import re
import sys
import asyncio
from dataclasses import dataclass
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
    from prompt_toolkit.formatted_text import (
        StyleAndTextTuples,
        fragment_list_width,
        to_formatted_text,
    )
    from prompt_toolkit.formatted_text.base import OneStyleAndTextTuple
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import Frame
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
    from prompt_toolkit.layout.utils import explode_text_fragments
    from prompt_toolkit.layout.containers import ScrollOffsets
    from prompt_toolkit.layout.menus import (
        CompletionsMenuControl,
    )
    from prompt_toolkit.utils import get_cwidth
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


@dataclass(frozen=True)
class SearchHighlightState:
    """CACHED SEARCH SNAPSHOT FOR HIGHLIGHTING AND STATUS RENDERING."""

    query: str
    matches: tuple[int, ...]
    active_match: int | None
    active_ordinal: int


class SearchMatchProcessor(Processor):
    """HIGHLIGHTS SEARCH MATCHES WITH DISTINCT ACTIVE AND PASSIVE STYLES."""

    def __init__(self, get_state: Callable[[], SearchHighlightState | None]):
        self.get_state = get_state

    def apply_transformation(self, transformation_input):
        state = self.get_state()
        if state is None or not state.query or not state.matches:
            return Transformation(transformation_input.fragments)

        line_text = "".join(
            _fragment_text(fragment) for fragment in transformation_input.fragments
        )
        if not line_text:
            return Transformation(transformation_input.fragments)

        line_start = transformation_input.document.translate_row_col_to_index(
            transformation_input.lineno, 0
        )
        line_end = line_start + len(line_text)
        query_len = len(state.query)

        ranges: list[tuple[int, int, str]] = []
        for match_start in state.matches:
            match_end = match_start + query_len
            if match_end <= line_start:
                continue
            if match_start >= line_end:
                break

            start = max(0, match_start - line_start)
            end = min(len(line_text), match_end - line_start)
            style = (
                "class:search-match-active"
                if state.active_match == match_start
                else "class:search-match"
            )
            ranges.append((start, end, style))

        if not ranges:
            return Transformation(transformation_input.fragments)

        new_fragments = []
        char_index = 0
        for fragment in transformation_input.fragments:
            base_style = cast(str, fragment[0])
            text = _fragment_text(fragment)
            if not text:
                new_fragments.append(fragment)
                continue

            segment_start = char_index
            segment_end = char_index + len(text)
            cursor = segment_start

            for range_start, range_end, highlight_style in ranges:
                if range_end <= segment_start or range_start >= segment_end:
                    continue

                overlap_start = max(segment_start, range_start)
                overlap_end = min(segment_end, range_end)

                if overlap_start > cursor:
                    new_fragments.append(
                        (
                            base_style,
                            text[
                                cursor - segment_start : overlap_start - segment_start
                            ],
                        )
                    )
                new_fragments.append(
                    (
                        f"{base_style} {highlight_style}".strip(),
                        text[
                            overlap_start - segment_start : overlap_end - segment_start
                        ],
                    )
                )
                cursor = overlap_end

            if cursor < segment_end:
                new_fragments.append((base_style, text[cursor - segment_start :]))

            char_index = segment_end

        return Transformation(new_fragments)


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
            self.mention_pattern = re.compile(r"<@[^>\n]+(?:>|$)|\[@[^\]\n]*(?:\]|$)")
            self._validation_cache: dict[tuple[int, str], bool] = {}
            self._invalid_fence_cache: dict[int, set[int]] = {}

        def get_invalid_fence_lines(self, document: Document) -> set[int]:
            """FLAGS ONLY THE LAST UNMATCHED FENCE LINE TO AVOID NOISY HIGHLIGHTING."""
            cache_key = id(document.text)
            cached = self._invalid_fence_cache.get(cache_key)
            if cached is not None:
                return cached

            fence_lines = [
                lineno
                for lineno, line in enumerate(document.lines)
                if line.lstrip().startswith("```")
            ]
            invalid_lines = {fence_lines[-1]} if len(fence_lines) % 2 else set()
            self._invalid_fence_cache = {cache_key: invalid_lines}
            return invalid_lines

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
            invalid_fence_lines = self.get_invalid_fence_lines(document)

            def get_line(lineno: int):
                original_tokens = get_original_line(lineno)
                text = document.lines[lineno]
                matches = list(self.mention_pattern.finditer(text))

                if not matches:
                    if lineno in invalid_fence_lines:
                        return [("class:invalid-syntax", text)]
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

                if lineno in invalid_fence_lines:
                    return [("class:invalid-syntax", text)]

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

    MIN_LABEL_COLUMN_WIDTH = 16
    MIN_META_COLUMN_WIDTH = 12
    MIN_WIDTH_FOR_META = 28
    MAX_VIEWPORT_WIDTH_RATIO = 0.72
    MAX_LABEL_WIDTH_RATIO = 0.58
    MAX_META_WIDTH_RATIO = 0.5

    def _get_display_text_width(self, text: str) -> int:
        """MEASURES PLAIN DISPLAY TEXT CONSISTENTLY WITH PROMPT-TOOLKIT CELLS."""
        return get_cwidth(text)

    def _trim_formatted_text_left(
        self, formatted_text: StyleAndTextTuples, max_width: int
    ) -> tuple[StyleAndTextTuples, int]:
        """TRIMS FROM THE LEFT SO LONG PATHS KEEP THEIR MOST RELEVANT TAIL."""
        width = fragment_list_width(formatted_text)
        if width <= max_width:
            return formatted_text, width

        if max_width <= 3:
            dots = "." * max(0, max_width)
            return [("", dots)], len(dots)

        remaining_width = max_width - 3
        tail: list[OneStyleAndTextTuple] = []

        for style_and_ch in reversed(list(explode_text_fragments(formatted_text))):
            ch_width = get_cwidth(style_and_ch[1])
            if ch_width <= remaining_width:
                tail.append(style_and_ch)
                remaining_width -= ch_width
            else:
                break

        tail.reverse()

        result: StyleAndTextTuples = [("", "...")]
        result.extend(tail)

        return result, max_width - remaining_width

    def _get_label_fragments(
        self, completion: Completion, is_current_completion: bool, width: int
    ) -> StyleAndTextTuples:
        """RENDERS THE LABEL COLUMN WITH SUFFIX-FIRST TRIMMING ON OVERFLOW."""
        if is_current_completion:
            style_str = f"class:completion-menu.completion.current {completion.style} {completion.selected_style}"
        else:
            style_str = "class:completion-menu.completion " + completion.style

        text, text_width = self._trim_formatted_text_left(
            to_formatted_text(completion.display), width - 1
        )
        padding = " " * max(0, width - 1 - text_width)

        return to_formatted_text(
            cast(StyleAndTextTuples, []) + [("", " ")] + text + [("", padding)],
            style=style_str,
        )

    def _get_width_budget(self, max_available_width: int) -> int:
        """KEEPS THE POPUP RESPONSIVE BY CAPPING IT BELOW THE FULL VIEWPORT."""
        if max_available_width <= self.MIN_WIDTH_FOR_META:
            return max_available_width

        capped_width = int(max_available_width * self.MAX_VIEWPORT_WIDTH_RATIO)
        return max(self.MIN_WIDTH_FOR_META, min(max_available_width, capped_width))

    def preferred_width(self, max_available_width: int) -> int | None:
        complete_state = get_app().current_buffer.complete_state
        if not complete_state:
            return 0

        width_budget = self._get_width_budget(max_available_width)
        menu_width = self._get_menu_width(width_budget, complete_state)
        menu_meta_width = self._get_menu_meta_width(
            max(0, width_budget - menu_width), complete_state
        )
        preferred = menu_width + menu_meta_width
        return min(width_budget, preferred)

    def _get_column_widths(self, width: int, complete_state) -> tuple[int, int, bool]:
        """SPLITS AVAILABLE WIDTH BETWEEN THE LABEL AND THE PATH META COLUMN."""
        show_meta = self._show_meta(complete_state)
        natural_label_width = self._get_menu_width(width, complete_state)
        natural_meta_width = self._get_menu_meta_width(width, complete_state)

        if not show_meta or width < self.MIN_WIDTH_FOR_META:
            return min(width, natural_label_width), 0, False

        label_content_width = max(self.MIN_WIDTH, natural_label_width)
        meta_content_width = max(self.MIN_META_COLUMN_WIDTH, natural_meta_width)
        natural_total = label_content_width + meta_content_width
        label_ratio = label_content_width / natural_total if natural_total else 0.5
        label_ratio = max(0.4, min(self.MAX_LABEL_WIDTH_RATIO, label_ratio))

        label_width = max(
            self.MIN_LABEL_COLUMN_WIDTH,
            min(int(width * label_ratio), int(width * self.MAX_LABEL_WIDTH_RATIO)),
        )
        label_width = min(label_width, width - self.MIN_META_COLUMN_WIDTH)
        meta_width = width - label_width

        max_meta_width = max(
            self.MIN_META_COLUMN_WIDTH, int(width * self.MAX_META_WIDTH_RATIO)
        )
        if meta_width > max_meta_width:
            shift = meta_width - max_meta_width
            meta_width -= shift
            label_width = min(width - meta_width, label_width + shift)

        label_width = min(label_width, natural_label_width)
        meta_width = width - label_width

        if (
            label_width < self.MIN_LABEL_COLUMN_WIDTH
            or meta_width < self.MIN_META_COLUMN_WIDTH
        ):
            return min(width, natural_label_width), 0, False

        if natural_meta_width < self.MIN_META_COLUMN_WIDTH:
            return min(width, natural_label_width), 0, False

        meta_width = min(
            meta_width,
            max(self.MIN_META_COLUMN_WIDTH, natural_meta_width),
        )
        label_width = width - meta_width

        if label_width < self.MIN_LABEL_COLUMN_WIDTH:
            return min(width, natural_label_width), 0, False

        return label_width, meta_width, True

    def _get_menu_item_meta_fragments(
        self, completion: Completion, is_current_completion: bool, width: int
    ) -> StyleAndTextTuples:
        """RENDERS PATH META FROM THE RIGHT SO THE LAST SEGMENTS STAY VISIBLE."""
        if is_current_completion:
            style_str = "class:completion-menu.meta.completion.current"
        else:
            style_str = "class:completion-menu.meta.completion"

        text, text_width = self._trim_formatted_text_left(
            to_formatted_text(completion.display_meta), width - 2
        )
        padding = " " * max(0, width - 1 - text_width)

        return to_formatted_text(
            cast(StyleAndTextTuples, []) + [("", " ")] + text + [("", padding)],
            style=style_str,
        )

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
            result = self._get_label_fragments(
                completion, is_current_completion, menu_width
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
        self.search_visible = False
        self.search_message = ""
        self.search_buffer = Buffer(
            document=Document("", cursor_position=0),
            multiline=False,
        )
        self._search_last_query = ""
        self._search_last_direction = 1
        self._search_last_match = -1
        self._search_cache_text_id = 0
        self._search_cache_cursor = -1
        self._search_cache_query = ""
        self._search_cache_state: SearchHighlightState | None = None
        self.search_buffer.on_text_changed += self._handle_search_text_changed

        self.search_window = VSplit(
            [
                Window(
                    content=FormattedTextControl(
                        lambda: " search " if self.search_visible else ""
                    ),
                    style="class:search-label",
                    width=Dimension(preferred=10),
                ),
                Window(
                    content=BufferControl(buffer=self.search_buffer),
                    style="class:search-input",
                    height=1,
                ),
                Window(
                    content=FormattedTextControl(self._get_search_status_text),
                    style="class:search-status",
                    align=WindowAlign.RIGHT,
                ),
            ],
            height=1,
            style="class:search-bar",
        )

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
            SearchMatchProcessor(self._get_search_highlight_state),
        ]

        self.main_window = Window(
            content=BufferControl(
                buffer=self.buffer,
                lexer=lexer,
                input_processors=processors,
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

    def _get_search_status_text(self) -> str:
        """RETURNS SEARCH MODE HINTS OR THE LAST SEARCH RESULT MESSAGE."""
        state = self._get_search_highlight_state()
        if self.search_message:
            return f" {self.search_message} "
        if state and state.query:
            if not state.matches:
                return " 0 of 0  [Enter] next  [Ctrl+R] prev  [Esc] close "
            return (
                f" {state.active_ordinal} of {len(state.matches)}"
                "  [Enter] next  [Ctrl+R] prev  [Esc] close "
            )
        return " [Enter] next  [Ctrl+R] prev  [Esc] close "

    def _handle_search_text_changed(self, _buffer: Buffer) -> None:
        """CLEARS STALE SEARCH NAVIGATION STATE AFTER QUERY EDITS."""
        self.search_message = ""
        self._search_last_query = ""
        self._search_last_direction = 1
        self._search_last_match = -1
        self._search_cache_state = None
        try:
            get_app().invalidate()
        except Exception:
            pass

    def _get_search_highlight_state(self) -> SearchHighlightState | None:
        """RETURNS A CACHED SEARCH SNAPSHOT TO AVOID REPEATED FULL-SCAN WORK."""
        if not self.search_visible:
            return None

        query = self.search_buffer.text
        text = self.buffer.text
        cursor = self.buffer.cursor_position
        text_id = id(text)
        if (
            self._search_cache_state is not None
            and self._search_cache_text_id == text_id
            and self._search_cache_query == query
            and self._search_cache_cursor == cursor
        ):
            return self._search_cache_state

        if not query:
            state = SearchHighlightState("", tuple(), None, 0)
        else:
            matches: list[int] = []
            start = 0
            while True:
                match_pos = text.find(query, start)
                if match_pos == -1:
                    break
                matches.append(match_pos)
                start = match_pos + 1

            active_match = None
            active_ordinal = 0
            if matches:
                cursor_match = next(
                    (
                        match
                        for match in matches
                        if match <= cursor < match + len(query)
                    ),
                    None,
                )
                if cursor_match is not None:
                    active_match = cursor_match
                elif (
                    self._search_last_query == query
                    and self._search_last_match in matches
                ):
                    active_match = self._search_last_match
                else:
                    active_match = next(
                        (match for match in matches if match >= cursor), matches[0]
                    )

                active_ordinal = matches.index(active_match) + 1

            state = SearchHighlightState(
                query, tuple(matches), active_match, active_ordinal
            )

        self._search_cache_text_id = text_id
        self._search_cache_cursor = cursor
        self._search_cache_query = query
        self._search_cache_state = state
        return state

    def _focus_search(self) -> None:
        """MOVES INPUT FOCUS INTO THE SEARCH FIELD IF AN APP IS ACTIVE."""
        try:
            get_app().layout.focus(self.search_buffer)
        except Exception:
            pass

    def _focus_main(self) -> None:
        """RESTORES INPUT FOCUS TO THE MAIN EDITOR BUFFER."""
        try:
            get_app().layout.focus(self.main_window)
        except Exception:
            pass

    def open_search(self) -> None:
        """SHOWS THE SEARCH BAR AND PREPARES IT FOR IMMEDIATE INPUT."""
        self.search_visible = True
        self.search_message = ""
        self._search_cache_state = None
        self.search_buffer.cursor_position = len(self.search_buffer.text)
        self._focus_search()

    def close_search(self) -> None:
        """HIDES THE SEARCH BAR AND RETURNS FOCUS TO THE EDITOR."""
        self.search_visible = False
        self.search_message = ""
        self._search_last_query = ""
        self._search_last_direction = 1
        self._search_last_match = -1
        self._search_cache_state = None
        self._focus_main()

    def open_help(self) -> None:
        """SHOWS THE HELP OVERLAY AND FOCUSES IT."""
        self.help_visible = True
        self.help_window.content.buffer.cursor_position = 0
        try:
            get_app().layout.focus(self.help_window)
        except Exception:
            pass

    def close_help(self) -> None:
        """HIDES THE HELP OVERLAY AND RETURNS FOCUS TO THE ACTIVE EDIT TARGET."""
        self.help_visible = False
        if self.search_visible:
            self._focus_search()
        else:
            self._focus_main()

    def toggle_help(self) -> None:
        """TOGGLES HELP VISIBILITY WITHOUT LOSING THE ACTIVE SEARCH CONTEXT."""
        if self.help_visible:
            self.close_help()
        else:
            self.open_help()

    def _find_search_match(
        self, query: str, start: int, direction: int
    ) -> tuple[int | None, bool]:
        """SEARCHES FORWARD OR BACKWARD AND REPORTS WHETHER THE RESULT WRAPPED."""
        text = self.buffer.text
        if direction > 0:
            pos = text.find(query, max(0, start))
            if pos != -1:
                return pos, False
            return (text.find(query), True) if query else (None, False)

        bounded_start = min(max(start, 0), len(text))
        pos = text.rfind(query, 0, bounded_start + len(query))
        if pos != -1:
            return pos, False
        return (text.rfind(query), True) if query else (None, False)

    def search_step(self, direction: int) -> bool:
        """MOVES TO THE NEXT OR PREVIOUS SEARCH MATCH WHILE KEEPING SEARCH OPEN."""
        query = self.search_buffer.text
        if not query:
            self.search_message = "enter a query"
            return False

        repeated = (
            query == self._search_last_query
            and direction == self._search_last_direction
            and self.buffer.cursor_position == self._search_last_match
        )
        start = self.buffer.cursor_position
        if direction > 0 and repeated:
            start += 1 if direction > 0 else -1
        elif direction < 0:
            start -= 1

        match_pos, wrapped = self._find_search_match(query, start, direction)
        if match_pos is None or match_pos < 0:
            self.search_message = "not found"
            return False

        self.buffer.cursor_position = match_pos
        self._search_last_query = query
        self._search_last_direction = direction
        self._search_last_match = match_pos
        self._search_cache_state = None
        self.search_message = "wrapped" if wrapped else ""
        return True

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

        body = HSplit(
            [
                top_bar,
                self.main_window,
                ConditionalContainer(
                    content=self.search_window,
                    filter=Condition(lambda: self.search_visible),
                ),
                bottom_toolbar,
            ]
        )

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
                "search-bar": "bg:#1f1f1f #ffffff",
                "search-label": "bg:#1f1f1f #00ffff bold",
                "search-input": "bg:#2d2d2d #ffffff",
                "search-status": "bg:#1f1f1f #ffff00",
                "search-match": "bg:#6b5f00 #fff4b3",
                "search-match-active": "bg:#005a9c #ffffff bold",
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
        app.ttimeoutlen = 0.05

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

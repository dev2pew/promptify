"""Terminal editor built on prompt-toolkit and Pygments"""

import re
import sys
import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable, Iterable, Literal, cast

from .logger import log
from .suggestions import AUTO_SUGGESTION_STYLE, PrefixSuggestion
from ..core.indexer import ProjectIndexer
from ..core.resolver import PromptResolver
from ..core.mods import (
    ModRegistry,
    parse_git_mention_query,
    split_file_query_and_range,
    split_git_branch_prefix,
)
from ..core.settings import APP_SETTINGS
from ..core.terminal import APP_TERMINAL_PROFILE, TerminalProfile
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
    from prompt_toolkit.layout.margins import Margin, NumberedMargin, ScrollbarMargin
    from prompt_toolkit.data_structures import Point
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.formatted_text import (
        StyleAndTextTuples,
        AnyFormattedText,
        fragment_list_width,
        to_formatted_text,
    )
    from prompt_toolkit.formatted_text.base import OneStyleAndTextTuple
    from prompt_toolkit.styles import Style
    from prompt_toolkit.lexers import Lexer
    from prompt_toolkit.filters import (
        Condition,
        FilterOrBool,
        has_completions,
        is_done,
        to_filter,
    )
    from prompt_toolkit.layout.processors import (
        AppendAutoSuggestion,
        BeforeInput,
        HighlightMatchingBracketProcessor,
        Processor,
        Transformation,
    )
    from prompt_toolkit.selection import SelectionState
    from prompt_toolkit.layout.utils import explode_text_fragments
    from prompt_toolkit.layout.containers import ScrollOffsets
    from prompt_toolkit.layout.menus import (
        CompletionsMenuControl,
    )
    from prompt_toolkit.utils import get_cwidth
except ImportError:
    log.err(
        get_string(
            "err_prompt_toolkit_missing",
            "'prompt_toolkit' library is missing. install it using: 'uv pip install prompt_toolkit'",
        )
    )
    sys.exit(1)


def _fragment_text(fragment: tuple[object, ...]) -> str:
    """Read prompt-toolkit fragments that may carry an optional third field"""
    if len(fragment) < 2 or not isinstance(fragment[1], str):
        return ""
    return fragment[1]


def _flatten_fragments_to_chars(
    fragments: StyleAndTextTuples,
) -> list[tuple[str, str]]:
    """Flatten fragments into style and character pairs for safe rewrites"""
    chars = []
    for fragment in fragments:
        style = cast(str, fragment[0])
        for char in _fragment_text(fragment):
            chars.append((style, char))
    return chars


def _append_original_token_range(
    tokens: list[tuple[str | None, str]],
    chars: list[tuple[str, str]],
    start: int,
    end: int,
) -> None:
    """Restore a style-preserving token slice from flattened character data"""
    curr_style = None
    curr_text: list[str] = []

    for i in range(start, end):
        style, char = chars[i]
        if style != curr_style:
            if curr_text:
                tokens.append((curr_style, "".join(curr_text)))
            curr_style = style
            curr_text = [char]
        else:
            curr_text.append(char)

    if curr_text:
        tokens.append((curr_style, "".join(curr_text)))


try:
    import pygments  # NOQA: F401
    from pygments.lexers.markup import MarkdownLexer
    from prompt_toolkit.lexers import PygmentsLexer

    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False
    log.warn(
        get_string(
            "err_pygments_missing",
            "'pygments' library is missing. syntax highlighting will be disabled. install it using: 'uv pip install pygments'",
        )
    )

try:
    from rapidfuzz import process  # NOQA: F401
except ImportError:
    log.err(
        get_string(
            "err_rapidfuzz_missing",
            "'rapidfuzz' library is missing. install it using: 'uv pip install rapidfuzz'",
        )
    )
    sys.exit(1)


MENTION_SCAN_PATTERN = r"<@(?:\\.|[^>\n])+(?:>|$)|\[@[^\]\n]*(?:\]|$)"
HELP_TOKEN_PATTERN = r"(<@(?:\\.|[^>\n])+>|\[@project\])|(\^?\[[^\]\n]+\])"
JUMP_TARGET_PATTERN = re.compile(r"^:(?P<line>\d+)(?:(?:[:,])(?P<column>\d+))?$")
HELP_TEXT_FALLBACK = (
    "[ general ]\n\n"
    "^[G] / [F1]                   : help\n"
    "^[F]                          : search\n"
    "^[R]                          : replace\n"
    "[Alt] + [G]                   : jump to line\n"
    "[Alt] + [Z]                   : toggle word wrap\n"
    "^[S]                          : resolve\n"
    "^[Q]                          : abort\n\n"
    "[ search ]\n\n"
    "[Enter] / [Shift] + [Enter]   : next / previous\n"
    "[^/v]                         : search history\n"
    "[F6] / [F7] / [F8]            : case / word / regex\n"
    "[Esc]                         : close\n\n"
    "[ replace ]\n\n"
    "[Enter]                       : replace\n"
    "^[Alt] + [Enter]              : replace all\n"
    "^[F6]                         : preserve case\n"
    "[Esc]                         : close\n\n"
    "[ jump ]\n\n"
    "[Enter]                       : jump\n"
    "[Esc]                         : close\n\n"
    "[ issues ]\n\n"
    "[Enter] / ^[N]                : next\n"
    "^[R] / ^[P]                   : previous\n"
    "[Esc]                         : close\n\n"
    "[ autocomplete mentions ]\n\n"
    "<@file:path>                  : file\n"
    "<@file:path:range>            : sliced file\n\n"
    "            first n           : head\n"
    "            last n            : tail\n"
    "            n-m               : ranged\n"
    "            #n                : single\n\n"
    "<@dir:path>                   : directory\n"
    "<@tree:path>                  : tree view\n"
    "<@tree:path:level>            : set depth\n"
    "<@ext:list>                   : type\n"
    "<@symbol:path:name>           : symbol\n"
    "<@git:diff>                   : work tree diff\n"
    "<@git:diff:path>              : work tree file diff\n"
    "<@git:status>                 : work tree status\n"
    "<@git:log>                    : recent log (20)\n"
    "<@git:log:count>              : set length\n"
    "<@git:history>                : recent log w/diff (5)\n"
    "<@git:history:count>          : set length\n"
    "<@git:[branch]:subcommand>    : set branch-scope\n"
    "<@git:[branch]:diff:path>     : ex.\n"
    "<@git:[branch]:log:count>     : ex.\n"
    "<@git:[branch]:history:count> : ex.\n"
    "[@project]                    : project structure\n\n"
    "[ editing ]\n\n"
    "^[A]                          : select all\n"
    "[Shift]                       : select\n"
    "^[Z/Y]                        : undo / redo\n"
    "^[C/X/V]                      : copy / cut / paste\n"
    "[Tab]                         : indent / autocomplete\n"
    "[Shift] + [Tab]               : unindent\n"
    "[Alt]   + [^/v]               : shift cursor\n"
    "^[/]                          : comment out\n"
    "^[W/Del]                      : delete previous / next\n"
    "[Enter]                       : newline / accept\n\n"
    "[ navigation ]\n\n"
    "[^/v/</>]                     : move\n"
    "^[^/v/</>]                    : next / previous\n"
    "[Home/End]                    : start / end\n"
    "^[Home/End]                   : file start / end\n"
    "^[PgUp/PgDn]                  : up / down (15x)\n\n"
    "press [Enter], [F1] or ^[G] to close\n"
)


class HighlightTrailingWhitespaceProcessor(Processor):
    """Highlight trailing spaces and tabs at the end of each line"""

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
    """Visually indicate a missing EOF newline"""

    def __init__(self, terminal_profile: TerminalProfile):
        self.terminal_profile = terminal_profile

    def apply_transformation(self, transformation_input):
        document = transformation_input.document
        lineno = transformation_input.lineno
        tokens = transformation_input.fragments

        if lineno == document.line_count - 1:
            if document.text.endswith("\n") or not document.text:
                tokens = tokens + [
                    ("class:eof-newline", self.terminal_profile.eof_newline_present)
                ]
            else:
                tokens = tokens + [
                    ("class:eof-newline", self.terminal_profile.eof_newline_missing)
                ]

        return Transformation(tokens)


@dataclass(frozen=True)
class SearchMatch:
    """Store one resolved search span in the active document"""

    start: int
    end: int


@dataclass(frozen=True)
class SearchHighlightState:
    """Cached search snapshot used for highlighting and status rendering"""

    query: str
    matches: tuple[SearchMatch, ...]
    active_match: SearchMatch | None
    active_ordinal: int


@dataclass(frozen=True)
class MentionValidationResult:
    """Capture whether a mention is valid, malformed, or unresolved"""

    style: str | None
    message: str | None


@dataclass(frozen=True)
class EditorIssue:
    """Represent a navigable editor issue in the current document"""

    line: int
    column: int
    end_column: int
    style: str
    message: str
    fragment: str


FocusTarget = Literal["main", "search", "replace", "jump", "help", "error", "quit"]
OverlayName = Literal["none", "help", "error", "quit"]


@dataclass(frozen=True)
class EditorViewState:
    """Capture editor and search state so overlays can restore it predictably"""

    focus: FocusTarget
    main_cursor: int
    search_cursor: int
    replace_cursor: int
    jump_cursor: int
    main_selection: SelectionState | None
    search_selection: SelectionState | None
    replace_selection: SelectionState | None
    jump_selection: SelectionState | None


@dataclass(slots=True)
class SearchOptions:
    """Track the live search and replace flags exposed by the widget"""

    match_case: bool = False
    match_whole_word: bool = False
    regex: bool = False
    preserve_case: bool = False

    def copy(self) -> "SearchOptions":
        """Create a detached snapshot for cache comparisons"""
        return SearchOptions(
            match_case=self.match_case,
            match_whole_word=self.match_whole_word,
            regex=self.regex,
            preserve_case=self.preserve_case,
        )


def parse_jump_target(text: str) -> tuple[int, int] | None:
    """Parse a 1-based line and optional character target from the jump bar"""
    match = JUMP_TARGET_PATTERN.fullmatch(text.strip())
    if match is None:
        return None

    line = int(match.group("line"))
    column_text = match.group("column")
    column = 1 if column_text is None else int(column_text)
    return line, column


def build_jump_target(line: int, column: int) -> str:
    """Format a 1-based cursor location for jump-mode display and parsing"""
    return f":{line}:{column}"


def _preserve_replacement_case(source: str, replacement: str) -> str:
    """Mirror simple source casing patterns onto a replacement string"""
    if not source or not replacement:
        return replacement
    if source.isupper():
        return replacement.upper()
    if source.islower():
        return replacement.lower()
    if source.istitle():
        return replacement.title()
    if len(source) == 1 and source.isalpha():
        return replacement.upper() if source.isupper() else replacement.lower()
    if source[0].isupper() and source[1:].islower():
        head = replacement[:1].upper()
        tail = replacement[1:].lower()
        return head + tail
    return replacement


class SearchMatchProcessor(Processor):
    """Highlight search matches with distinct active and passive styles"""

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
        ranges: list[tuple[int, int, str]] = []
        for match in state.matches:
            match_start = match.start
            match_end = match.end
            if match_end <= line_start:
                continue
            if match_start >= line_end:
                break

            start = max(0, match_start - line_start)
            end = min(len(line_text), match_end - line_start)
            style = (
                "class:search-match-active"
                if state.active_match == match
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


class ActiveLineProcessor(Processor):
    """Highlight the active editor row without altering the document text"""

    def apply_transformation(self, transformation_input):
        if (
            transformation_input.lineno
            != transformation_input.document.cursor_position_row
        ):
            return Transformation(transformation_input.fragments)

        fragments = []
        for fragment in transformation_input.fragments:
            style = cast(str, fragment[0])
            fragments.append(
                (
                    f"class:current-line {style}".strip(),
                    _fragment_text(fragment),
                )
            )
        return Transformation(fragments)


class VerticalSeparatorMargin(Margin):
    """Render a one-column separator between the gutter and editor content"""

    def __init__(self, terminal_profile: TerminalProfile):
        self._separator = terminal_profile.border.vertical

    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        return 1

    def create_margin(self, window_render_info, width: int, height: int):
        return [("class:editor-frame.border", (self._separator + "\n") * height)]


if HAS_PYGMENTS:

    def tokenize_mention(text: str) -> list[tuple[str, str]]:
        """Tokenize mentions with semantic parsing for their arguments"""
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
            parsed = parse_git_mention_query(rest)
            if parsed is not None:
                add_sep()
                branch, raw_branch, remainder = split_git_branch_prefix(rest) or (
                    None,
                    None,
                    rest,
                )
                if branch is not None and raw_branch is not None:
                    tokens.append(("class:mention-path", f"[{raw_branch}]"))
                    add_sep()
                command = parsed.command
                tokens.append(("class:mention-git-cmd", command))
                if parsed.argument is not None:
                    add_sep()
                    argument = str(parsed.argument)
                    argument_style = (
                        "class:mention-path"
                        if command == "diff"
                        else "class:mention-range"
                    )
                    tokens.append((argument_style, argument))
            else:
                branch, raw_branch, remainder = split_git_branch_prefix(rest) or (
                    None,
                    None,
                    rest,
                )
                add_sep()
                if branch is not None and raw_branch is not None:
                    tokens.append(("class:mention-path", f"[{raw_branch}]"))
                    if remainder:
                        add_sep()
                        tokens.append(("class:mention-git-cmd", remainder))
                else:
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
        """Custom lexer for tag highlighting and invalid-mention detection"""

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
            self.mention_pattern = re.compile(MENTION_SCAN_PATTERN)
            self._validation_cache: dict[tuple[int, str], MentionValidationResult] = {}
            self._invalid_fence_cache: dict[int, set[int]] = {}

        def get_invalid_fence_lines(self, document: Document) -> set[int]:
            """Flag only the last unmatched fence line to avoid noisy highlighting"""
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

        def _cache_validation_result(
            self,
            cache_key: tuple[int, str],
            style: str | None,
            message: str | None,
        ) -> MentionValidationResult:
            """Store and return a validation result in one step"""
            result = MentionValidationResult(style, message)
            self._validation_cache[cache_key] = result
            return result

        def _validate_safe_path(
            self,
            path: str,
            label: str = "path",
        ) -> MentionValidationResult | None:
            """Report paths that escape the project root"""
            if not self.resolver.context.is_safe_query_path(path):
                return MentionValidationResult(
                    "unresolved-reference",
                    get_string(
                        "issue_path_outside_project",
                        "{label} '{path}' is outside the project",
                    ).format(label=label, path=path),
                )
            return None

        def _validate_indexed_path(
            self,
            path: str,
            missing_message: str,
            unsafe_message: str | None = None,
        ) -> MentionValidationResult | None:
            """Validate that a query path is safe and resolves to a file"""
            path_issue = self._validate_safe_path(path)
            if path_issue is not None:
                if unsafe_message is not None:
                    return MentionValidationResult(
                        path_issue.style,
                        unsafe_message,
                    )
                return path_issue

            if not self.indexer.find_matches(path):
                return MentionValidationResult(
                    "unresolved-reference",
                    missing_message,
                )
            return None

        def inspect_mention(self, text: str) -> MentionValidationResult:
            """Classify a mention as valid, malformed, or unresolved"""
            cache_key = (self.indexer.revision, text)
            cached = self._validation_cache.get(cache_key)
            if cached is not None:
                return cached

            if text == "[@project]":
                return self._cache_validation_result(cache_key, None, None)
            if not text.endswith(">"):
                return self._cache_validation_result(
                    cache_key,
                    "invalid-syntax",
                    get_string(
                        "issue_incomplete_mention_syntax",
                        "incomplete mention syntax",
                    ),
                )

            pattern = self.registry.pattern
            if pattern is None:
                self.registry.build()
                pattern = self.registry.pattern
            if pattern is None:
                return self._cache_validation_result(
                    cache_key,
                    "invalid-syntax",
                    get_string(
                        "issue_mention_registry_unavailable",
                        "mention registry is unavailable",
                    ),
                )

            match = pattern.fullmatch(text)
            if not match:
                return self._cache_validation_result(
                    cache_key,
                    "invalid-syntax",
                    get_string(
                        "issue_malformed_mention_syntax",
                        "malformed mention syntax",
                    ),
                )

            try:
                mod, _ = self.registry.get_mod_and_text(match)

                if mod.name == "mod_file":
                    body = text.removeprefix("<@file:").removesuffix(">")
                    path, _ = split_file_query_and_range(body)
                    path_issue = self._validate_indexed_path(
                        path,
                        get_string(
                            "issue_file_unresolved",
                            "file '{path}' could not be resolved",
                        ).format(path=path),
                        unsafe_message=get_string(
                            "issue_file_unresolved",
                            "file '{path}' could not be resolved",
                        ).format(path=path),
                    )
                    if path_issue is not None:
                        return self._cache_validation_result(
                            cache_key,
                            path_issue.style,
                            path_issue.message,
                        )
                elif mod.name in ("mod_dir", "mod_tree"):
                    p = re.match(r"<@(dir|tree):([^>:]+)", text)
                    if p:
                        clean = p.group(2).replace("\\", "/").strip("/")
                        if clean == "":
                            return self._cache_validation_result(cache_key, None, None)
                        path_issue = self._validate_safe_path(clean)
                        if path_issue is not None:
                            return self._cache_validation_result(
                                cache_key,
                                path_issue.style,
                                path_issue.message,
                            )
                        if (
                            clean
                            and clean not in self.indexer.dirs
                            and not any(d.startswith(clean) for d in self.indexer.dirs)
                        ):
                            return self._cache_validation_result(
                                cache_key,
                                "unresolved-reference",
                                get_string(
                                    "issue_directory_unresolved",
                                    "directory '{path}' could not be resolved",
                                ).format(path=clean),
                            )
                elif mod.name == "mod_symbol":
                    p = re.match(r"<@symbol:([^>:]+?)(?::([^>]+))?>", text)
                    if not p:
                        return self._cache_validation_result(
                            cache_key,
                            "invalid-syntax",
                            get_string(
                                "issue_malformed_symbol_mention",
                                "malformed symbol mention",
                            ),
                        )
                    path = p.group(1)
                    path_issue = self._validate_indexed_path(
                        path,
                        get_string(
                            "issue_symbol_file_unresolved",
                            "symbol file '{path}' could not be resolved",
                        ).format(path=path),
                    )
                    if path_issue is not None:
                        return self._cache_validation_result(
                            cache_key,
                            path_issue.style,
                            path_issue.message,
                        )
                elif mod.name == "mod_ext":
                    p = re.match(r"<@(type|ext):([^>]+)>", text)
                    if not p:
                        return self._cache_validation_result(
                            cache_key,
                            "invalid-syntax",
                            get_string(
                                "issue_malformed_extension_mention",
                                "malformed extension mention",
                            ),
                        )
                    exts = [e.strip().lower() for e in p.group(2).split(",")]
                    if not self.indexer.get_by_extensions(exts):
                        return self._cache_validation_result(
                            cache_key,
                            "unresolved-reference",
                            get_string(
                                "issue_extensions_unresolved",
                                "no files found for extensions '{extensions}'",
                            ).format(extensions=p.group(2)),
                        )

                return self._cache_validation_result(cache_key, None, None)
            except Exception:
                return self._cache_validation_result(
                    cache_key,
                    "invalid-syntax",
                    get_string(
                        "issue_failed_to_parse_mention", "failed to parse mention"
                    ),
                )

        def is_valid_mention(self, text: str) -> bool:
            """Backward-compatibility helper for boolean validation callers"""
            return self.inspect_mention(text).style is None

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

                chars = _flatten_fragments_to_chars(original_tokens)

                new_tokens: list[tuple[str | None, str]] = []
                last_idx = 0

                for m in matches:
                    start, end = m.span()
                    m_text = m.group(0)

                    _append_original_token_range(new_tokens, chars, last_idx, start)

                    # INJECT GRANULAR MENTION TOKENS OR INVALID STYLING
                    if not self.expensive_checks_enabled():
                        new_tokens.extend(tokenize_mention(m_text))
                    else:
                        validation = self.inspect_mention(m_text)
                        if validation.style is None:
                            new_tokens.extend(tokenize_mention(m_text))
                        else:
                            new_tokens.append((f"class:{validation.style}", m_text))

                    last_idx = end

                _append_original_token_range(new_tokens, chars, last_idx, len(chars))

                if lineno in invalid_fence_lines:
                    return [("class:invalid-syntax", text)]

                return new_tokens

            return get_line


class HelpLexer(Lexer):
    """Regex-based lexer for help window text"""

    def __init__(self):

        # HEADERS: [ GENERAL ]
        self.header_re = re.compile(r"^\s*\[ .* \]\s*$")

        # MENTIONS OR KEYS: <@...> | [@PROJECT] | ^[X]
        self.combined_re = re.compile(HELP_TOKEN_PATTERN)

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
    """Route autocomplete requests through the registered mods"""

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
    """Completion menu control that respects the active viewport width"""

    MIN_LABEL_COLUMN_WIDTH = 16
    MIN_META_COLUMN_WIDTH = 12
    MIN_WIDTH_FOR_META = 28
    MAX_VIEWPORT_WIDTH_RATIO = 0.72
    MAX_LABEL_WIDTH_RATIO = 0.58
    MAX_META_WIDTH_RATIO = 0.5

    def _get_display_text_width(self, text: str) -> int:
        """Measure display text consistently with prompt-toolkit cell widths"""
        return get_cwidth(text)

    def _trim_formatted_text_left(
        self, formatted_text: StyleAndTextTuples, max_width: int
    ) -> tuple[StyleAndTextTuples, int]:
        """Trim from the left so long paths keep their most relevant tail"""
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
        """Render the label column with suffix-first trimming on overflow"""
        if is_current_completion:
            style_str = f"class:completion-menu.completion.current {completion.style} {completion.selected_style}"
        else:
            style_str = "class:completion-menu.completion " + completion.style

        return self._get_trimmed_column_fragments(
            to_formatted_text(completion.display),
            style_str,
            width,
            trim_delta=1,
        )

    def _get_trimmed_column_fragments(
        self,
        content: StyleAndTextTuples,
        style_str: str,
        width: int,
        trim_delta: int,
        padding_delta: int = 1,
    ) -> StyleAndTextTuples:
        """Trim and pad a single completion column consistently"""
        text, text_width = self._trim_formatted_text_left(content, width - trim_delta)
        padding = " " * max(0, width - padding_delta - text_width)

        return to_formatted_text(
            cast(StyleAndTextTuples, []) + [("", " ")] + text + [("", padding)],
            style=style_str,
        )

    def _get_width_budget(self, max_available_width: int) -> int:
        """Keep the popup responsive by capping it below the full viewport"""
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
        """Split available width between the label and path metadata columns"""
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
        """Render path metadata from the right so the tail stays visible"""
        if is_current_completion:
            style_str = "class:completion-menu.meta.completion.current"
        else:
            style_str = "class:completion-menu.meta.completion"

        return self._get_trimmed_column_fragments(
            to_formatted_text(completion.display_meta),
            style_str,
            width,
            trim_delta=2,
        )

    def create_content(self, width: int, height: int) -> UIContent:
        """Render completions using a viewport-aware label and metadata split"""
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
    """Dropdown menu that tracks terminal size instead of a fixed width hint"""

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
    """Manage the core prompt-toolkit terminal editor"""

    BULK_EDIT_SUSPEND_SECONDS = APP_SETTINGS.editor_behavior.bulk_edit_suspend_seconds
    BULK_EDIT_SIZE_THRESHOLD = APP_SETTINGS.editor_behavior.bulk_edit_size_threshold
    COMPLETION_MENU_MAX_HEIGHT = APP_SETTINGS.editor_layout.completion_menu_max_height
    COMPLETION_MENU_SCROLL_OFFSET = (
        APP_SETTINGS.editor_layout.completion_menu_scroll_offset
    )
    SEARCH_HISTORY_LIMIT = APP_SETTINGS.editor_behavior.search_history_limit
    TOKEN_UPDATE_INTERVAL = APP_SETTINGS.editor_behavior.token_update_interval

    def __init__(
        self,
        initial_text: str,
        indexer: ProjectIndexer,
        resolver: PromptResolver,
        show_help: bool | None = None,
        terminal_profile: TerminalProfile | None = None,
    ):
        if show_help is None:
            show_help = APP_SETTINGS.editor_behavior.show_help_on_start
        self._overlay_visibility: dict[OverlayName, bool] = {
            "help": False,
            "error": False,
            "quit": False,
        }
        self._overlay_restore_focus: dict[OverlayName, FocusTarget] = {
            "help": "main",
            "error": "main",
            "quit": "main",
        }
        self._overlay_suspended: dict[OverlayName, OverlayName] = {
            "help": "none",
            "error": "none",
            "quit": "none",
        }
        self._overlay_view_state: dict[OverlayName, EditorViewState | None] = {
            "help": None,
            "error": None,
            "quit": None,
        }
        self.help_visible = show_help
        self.terminal_profile = terminal_profile or APP_TERMINAL_PROFILE
        self.indexer = indexer
        self.resolver = resolver
        self.token_count = 0
        self._bulk_mode_until = 0.0
        self._token_estimate_busy = False
        self._passive_status = ""
        self._passive_status_transient = False
        self._search_message_transient = False
        self._search_history: list[str] = []
        self._search_history_index = -1
        self._search_history_draft = ""
        self._search_history_navigation_active = False
        self._document_issue_cache_text_id = 0
        self._document_issue_cache_enabled = True
        self._document_issue_cache: tuple[EditorIssue, ...] = tuple()
        self.issue_mode_active = False
        self.issue_index = 0
        self.word_wrap_enabled = APP_SETTINGS.editor_behavior.word_wrap
        self.search_options = SearchOptions()

        self.buffer = Buffer(
            document=Document(initial_text, cursor_position=0),
            completer=MentionCompleter(
                cast(ProjectIndexer, indexer),
                cast(ModRegistry, resolver.registry),
                self.should_complete,
            ),
            complete_while_typing=Condition(self.should_complete_while_typing),
        )
        self.buffer.on_text_changed += self._handle_buffer_text_changed
        self.result: str | None = None

        help_text = get_string("help_text", HELP_TEXT_FALLBACK)
        self._help_search_anchor = help_text.find("[ search ]")
        self._help_issue_anchor = help_text.find("[ issues ]")
        self.help_buffer = Buffer(document=Document(help_text), read_only=True)

        self.help_window = Window(
            content=BufferControl(buffer=self.help_buffer, lexer=HelpLexer()),
            style="class:help-text",
            wrap_lines=False,
            width=Dimension(
                min=APP_SETTINGS.editor_layout.help_width_min,
                max=APP_SETTINGS.editor_layout.help_width_max,
                weight=1,
            ),
            height=Dimension(
                min=APP_SETTINGS.editor_layout.help_height_min,
                max=APP_SETTINGS.editor_layout.help_height_max,
                weight=1,
            ),
        )

        self.err_visible = False
        self.err_message = ""
        self.err_buffer = Buffer(document=Document(""), read_only=True)
        self.err_window = Window(
            content=BufferControl(buffer=self.err_buffer),
            style="class:err-text",
            wrap_lines=True,
            width=Dimension(
                min=APP_SETTINGS.editor_layout.err_width_min,
                max=APP_SETTINGS.editor_layout.err_width_max,
                weight=1,
            ),
            height=Dimension(
                min=APP_SETTINGS.editor_layout.err_height_min,
                max=APP_SETTINGS.editor_layout.err_height_max,
                weight=1,
            ),
        )
        self.quit_visible = False
        self.quit_buffer = Buffer(
            document=Document(
                self.get_text(
                    "editor_quit_confirm",
                    "quit without saving?\nall progress will be discarded\n\n[Y/Enter] quit [N/Esc] cancel\n",
                )
            ),
            read_only=True,
        )
        self.quit_window = Window(
            content=BufferControl(buffer=self.quit_buffer),
            style="class:err-text",
            wrap_lines=True,
            width=Dimension(
                min=APP_SETTINGS.editor_layout.err_width_min,
                max=APP_SETTINGS.editor_layout.err_width_max,
                weight=1,
            ),
            height=Dimension(
                min=APP_SETTINGS.editor_layout.err_height_min,
                max=APP_SETTINGS.editor_layout.err_height_max,
                weight=1,
            ),
        )
        self.search_visible = False
        self.replace_visible = False
        self.search_message = ""
        self.search_buffer = Buffer(
            document=Document("", cursor_position=0),
            multiline=False,
        )
        self.replace_buffer = Buffer(
            document=Document("", cursor_position=0),
            multiline=False,
        )
        self._search_last_query = ""
        self._search_last_direction = 1
        self._search_last_match: SearchMatch | None = None
        self._search_cache_text_id = 0
        self._search_cache_cursor = -1
        self._search_cache_query = ""
        self._search_cache_options = SearchOptions()
        self._search_cache_state: SearchHighlightState | None = None
        self.search_buffer.on_text_changed += self._handle_search_text_changed
        self.replace_buffer.on_text_changed += self._handle_replace_text_changed

        self.search_window = self._build_search_widget()
        self.jump_visible = False
        self.jump_message = ""
        self.jump_buffer = Buffer(
            document=Document("", cursor_position=0),
            multiline=False,
            auto_suggest=PrefixSuggestion(self._get_jump_default_text),
        )
        self.jump_buffer.on_text_changed += self._handle_jump_text_changed

        self.jump_window = self._build_input_bar(
            self.jump_buffer,
            self._get_jump_label_text,
            self._get_jump_status_text,
            input_processors=[
                BeforeInput(":", style="class:search-label"),
                AppendAutoSuggestion(style="class:auto-suggestion"),
            ],
        )

        self.lexer = (
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
            EOFNewlineProcessor(self.terminal_profile),
            ActiveLineProcessor(),
            SearchMatchProcessor(self._get_search_highlight_state),
        ]

        self.main_window = Window(
            content=BufferControl(
                buffer=self.buffer,
                lexer=self.lexer,
                input_processors=processors,
            ),
            cursorline=True,
            wrap_lines=to_filter(self.word_wrap_enabled),
            left_margins=(
                [
                    NumberedMargin(relative=False, display_tildes=False),
                    VerticalSeparatorMargin(self.terminal_profile),
                ]
                if APP_SETTINGS.editor_behavior.show_line_numbers
                else []
            ),
        )
        self.completions_menu = ResponsiveCompletionsMenu(
            max_height=self.COMPLETION_MENU_MAX_HEIGHT,
            scroll_offset=self.COMPLETION_MENU_SCROLL_OFFSET,
        )

    def _build_input_bar(
        self,
        buffer: Buffer,
        get_label_text: Callable[[], str],
        get_status_text: Callable[[], str],
        *,
        input_processors: list[Processor] | None = None,
    ) -> VSplit:
        """Build the shared single-line chrome used by search and jump inputs"""
        return VSplit(
            [
                Window(
                    content=FormattedTextControl(get_label_text),
                    style="class:search-label",
                    width=Dimension(preferred=18),
                ),
                Window(
                    content=BufferControl(
                        buffer=buffer,
                        input_processors=input_processors or [],
                    ),
                    style="class:search-input",
                    height=1,
                ),
                Window(
                    content=FormattedTextControl(get_status_text),
                    style="class:search-status",
                    align=WindowAlign.RIGHT,
                ),
            ],
            height=1,
            style="class:search-bar",
        )

    def _build_search_widget(self) -> HSplit:
        """Build the shared VS Code-style search and replace widget"""
        search_row = self._build_input_bar(
            self.search_buffer,
            self._get_search_label_text,
            self._get_search_status_text,
        )
        replace_row = self._build_input_bar(
            self.replace_buffer,
            self._get_replace_label_text,
            self._get_replace_status_text,
        )
        return HSplit(
            [
                search_row,
                ConditionalContainer(
                    content=replace_row,
                    filter=Condition(lambda: self.replace_visible),
                ),
            ],
            style="class:search-bar",
        )

    def _build_style(self) -> Style:
        """Build the editor style map and fall back if config values are invalid"""
        try:
            styles = dict(APP_SETTINGS.theme.styles)
            styles.setdefault("auto-suggestion", AUTO_SUGGESTION_STYLE)
            return Style.from_dict(styles)
        except Exception:
            return Style.from_dict(
                {
                    "topbar": "bg:#333333 #ffffff",
                    "topbar-mode": "bg:#333333 #aee6ff bold",
                    "topbar-title": "bg:#333333 #00ffff bold",
                    "topbar-status": "bg:#333333 #ffd89a",
                    "topbar-tokens": "bg:#333333 #ffff00",
                    "toolbar": "bg:#333333 #ffffff",
                    "toolbar-right": "bg:#333333 #00ff00",
                    "completion-menu": "bg:#444444 #ffffff",
                    "completion-menu.completion.current": "bg:#1d6f62 #f5fffb bold",
                    "editor-frame.border": "fg:#4a4a4a",
                    "search-bar": "bg:#1f1f1f #ffffff",
                    "search-label": "bg:#1f1f1f #9fe9ff bold",
                    "search-input": "bg:#2d2d2d #ffffff",
                    "search-status": "bg:#1f1f1f #ffe09c",
                    "search-toggle-on": "bg:#1f1f1f #5fd75f bold",
                    "search-toggle-off": "bg:#1f1f1f #ff6b6b bold",
                    "search-match": "bg:#5d4a1d #fff0cb",
                    "search-match-active": "bg:#1f5d8e #f7fbff bold",
                    "current-line": "bg:#262a31",
                    "err-frame": "bg:#101317",
                    "err-frame.border": "fg:#768394",
                    "err-frame.label": "bg:#101317 #d7e6f6 bold",
                    "err-text": "bg:#171c22 #f2f5f8",
                    "mention-tag": "fg:#00ffff bold",
                    "mention-path": "fg:#ffaa00",
                    "mention-range": "fg:#ff55ff",
                    "mention-depth": "fg:#ff55ff",
                    "mention-ext": "fg:#ffaa00",
                    "mention-git-cmd": "fg:#00aa00",
                    "mention-class": "fg:#00ff00 bold",
                    "mention-function": "fg:#5555ff",
                    "mention-method": "fg:#55ffff",
                    "invalid-syntax": "bg:#7c1f24 #fff3f3",
                    "unresolved-reference": "bg:#6e4a1c #fff0d8",
                    "help-header": "fg:#00ff00 bold",
                    "help-key": "fg:#ffff00",
                    "trailing-whitespace": "bg:#ff0000",
                    "eof-newline": "fg:#ff0000",
                    "auto-suggestion": AUTO_SUGGESTION_STYLE,
                }
            )

    def _build_centered_overlay(
        self, container, visible_filter: Condition
    ) -> ConditionalContainer:
        """Center an interactive panel while allowing it to scale with the viewport"""
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

    def _build_chrome(self, body, title, style: str):
        """Build resize-safe chrome using ASCII or Unicode border glyphs"""
        border = self.terminal_profile.border
        border_style = f"{style}.border"
        label_style = f"{style}.label"
        has_title = bool(title)
        title_control = FormattedTextControl(
            (lambda: f" {title()} ") if callable(title) else f" {title} "
        )

        top_row = (
            VSplit(
                [
                    Window(
                        width=1,
                        height=1,
                        char=border.top_left,
                        style=border_style,
                    ),
                    Window(
                        width=1, height=1, char=border.horizontal, style=border_style
                    ),
                    Window(content=title_control, style=label_style, height=1),
                    Window(
                        width=1, height=1, char=border.horizontal, style=border_style
                    ),
                    Window(
                        width=1,
                        height=1,
                        char=border.top_right,
                        style=border_style,
                    ),
                ],
                height=1,
            )
            if has_title
            else VSplit(
                [
                    Window(
                        width=1,
                        height=1,
                        char=border.top_left,
                        style=border_style,
                    ),
                    Window(height=1, char=border.horizontal, style=border_style),
                    Window(
                        width=1,
                        height=1,
                        char=border.top_right,
                        style=border_style,
                    ),
                ],
                height=1,
            )
        )

        return HSplit(
            [
                top_row,
                VSplit(
                    [
                        Window(width=1, char=border.vertical, style=border_style),
                        body,
                        Window(width=1, char=border.vertical, style=border_style),
                    ],
                    padding=0,
                ),
                VSplit(
                    [
                        Window(
                            width=1,
                            height=1,
                            char=border.bottom_left,
                            style=border_style,
                        ),
                        Window(height=1, char=border.horizontal, style=border_style),
                        Window(
                            width=1,
                            height=1,
                            char=border.bottom_right,
                            style=border_style,
                        ),
                    ],
                    height=1,
                ),
            ],
            style=style,
        )

    def _build_modal_float(
        self,
        body,
        title,
        style: str,
        visible_filter: Condition,
    ) -> Float:
        """Build a centered modal float around resize-safe chrome"""
        frame = self._build_chrome(body, title, style)
        return Float(
            content=self._build_centered_overlay(frame, visible_filter),
            top=0,
            bottom=0,
            left=0,
            right=0,
        )

    def _copy_selection_state(
        self, selection_state: SelectionState | None
    ) -> SelectionState | None:
        """Clone a selection snapshot so help overlays can restore it cleanly"""
        if selection_state is None:
            return None
        return SelectionState(
            original_cursor_position=selection_state.original_cursor_position,
            type=selection_state.type,
        )

    def _restore_selection_state(
        self, buffer: Buffer, selection_state: SelectionState | None
    ) -> None:
        """Reapply a saved selection snapshot to a target buffer"""
        buffer.selection_state = self._copy_selection_state(selection_state)

    @property
    def help_visible(self) -> bool:
        """Expose help visibility while storing overlay state centrally"""
        return self._overlay_visibility["help"]

    @help_visible.setter
    def help_visible(self, value: bool) -> None:
        self._overlay_visibility["help"] = value

    @property
    def err_visible(self) -> bool:
        """Expose error visibility while storing overlay state centrally"""
        return self._overlay_visibility["error"]

    @err_visible.setter
    def err_visible(self, value: bool) -> None:
        self._overlay_visibility["error"] = value

    @property
    def quit_visible(self) -> bool:
        """Expose quit visibility while storing overlay state centrally"""
        return self._overlay_visibility["quit"]

    @quit_visible.setter
    def quit_visible(self, value: bool) -> None:
        self._overlay_visibility["quit"] = value

    def _set_overlay_visible(self, overlay: OverlayName, visible: bool) -> None:
        """Update overlay visibility through the shared registry"""
        if overlay == "none":
            return
        self._overlay_visibility[overlay] = visible

    def _get_visible_overlay(self) -> OverlayName:
        """Return the currently visible modal overlay, if any"""
        for overlay in ("help", "quit", "error"):
            if self._overlay_visibility[cast(OverlayName, overlay)]:
                return cast(OverlayName, overlay)
        return "none"

    def _get_focus_target(self) -> FocusTarget:
        """Describe which editor surface currently owns user attention"""
        overlay = self._get_visible_overlay()
        if overlay != "none":
            return cast(FocusTarget, overlay)
        if self.jump_visible:
            return "jump"
        if self.replace_visible:
            return "replace"
        if self.search_visible:
            return "search"
        return "main"

    def _capture_view_state(self) -> EditorViewState:
        """Snapshot editor input cursors plus selections for later restore"""
        return EditorViewState(
            focus=self._get_focus_target(),
            main_cursor=self.buffer.cursor_position,
            search_cursor=self.search_buffer.cursor_position,
            replace_cursor=self.replace_buffer.cursor_position,
            jump_cursor=self.jump_buffer.cursor_position,
            main_selection=self._copy_selection_state(self.buffer.selection_state),
            search_selection=self._copy_selection_state(
                self.search_buffer.selection_state
            ),
            replace_selection=self._copy_selection_state(
                self.replace_buffer.selection_state
            ),
            jump_selection=self._copy_selection_state(self.jump_buffer.selection_state),
        )

    def _restore_view_state(self, state: EditorViewState) -> None:
        """Restore editor input cursors plus selections from a snapshot"""
        self.buffer.cursor_position = state.main_cursor
        self.search_buffer.cursor_position = state.search_cursor
        self.replace_buffer.cursor_position = state.replace_cursor
        self.jump_buffer.cursor_position = state.jump_cursor
        self._restore_selection_state(self.buffer, state.main_selection)
        self._restore_selection_state(self.search_buffer, state.search_selection)
        self._restore_selection_state(self.replace_buffer, state.replace_selection)
        self._restore_selection_state(self.jump_buffer, state.jump_selection)

    def _focus_target(self, target: FocusTarget) -> None:
        """Route focus changes through one place for all editor surfaces"""
        if target == "search" and self.search_visible:
            self._focus(self.search_buffer)
        elif target == "replace" and self.search_visible and self.replace_visible:
            self._focus(self.replace_buffer)
        elif target == "jump" and self.jump_visible:
            self._focus(self.jump_buffer)
        elif target == "help" and self.help_visible:
            self._focus(self.help_window)
        elif target == "error" and self.err_visible:
            self._focus(self.err_window)
        elif target == "quit" and self.quit_visible:
            self._focus(self.quit_window)
        else:
            self._focus(self.main_window)

    def _show_overlay(
        self,
        overlay: OverlayName,
        *,
        restore_focus: FocusTarget | None = None,
        preserve_view: bool = False,
    ) -> OverlayName:
        """Show one overlay, suspending any currently visible overlay beneath it"""
        current_focus = restore_focus or self._get_focus_target()
        suspended = self._get_visible_overlay()
        if suspended != "none" and suspended != overlay:
            self._set_overlay_visible(suspended, False)
        elif suspended == overlay:
            suspended = self._overlay_suspended[overlay]

        self._overlay_suspended[overlay] = suspended
        self._overlay_restore_focus[overlay] = current_focus
        self._overlay_view_state[overlay] = (
            self._capture_view_state() if preserve_view else None
        )
        self._set_overlay_visible(overlay, True)
        return suspended

    def _hide_overlay(
        self, overlay: OverlayName, *, restore_view: bool = False
    ) -> None:
        """Hide one overlay and resume the previously suspended overlay or focus target"""
        suspended = self._overlay_suspended[overlay]
        restore_focus = self._overlay_restore_focus[overlay]
        view_state = self._overlay_view_state[overlay]

        self._set_overlay_visible(overlay, False)
        self._overlay_suspended[overlay] = "none"
        self._overlay_view_state[overlay] = None

        if restore_view and view_state is not None:
            self._restore_view_state(view_state)

        if suspended != "none":
            self._set_overlay_visible(suspended, True)
            self._focus_target(cast(FocusTarget, suspended))
        else:
            self._focus_target(restore_focus)

    def _focus(self, target) -> None:
        """Focus a target if an application is active"""
        try:
            get_app().layout.focus(target)
        except Exception:
            pass

    def invalidate(self) -> None:
        """Request a redraw when an application is active"""
        try:
            app = get_app()
        except Exception:
            return
        if app:
            app.invalidate()

    def get_text(self, key: str, default: str) -> str:
        """Read a localized UI string with an inline fallback"""
        return get_string(key, default)

    def format_text(self, key: str, default: str, /, **values: object) -> str:
        """Read and format a localized UI string with inline fallbacks"""
        return self.get_text(key, default).format(**values)

    def _set_help_cursor(self, position: int) -> None:
        """Move the help buffer cursor without reaching through untyped controls"""
        self.help_buffer.cursor_position = position

    def note_user_activity(self) -> None:
        """Clear transient status messages after the next user action"""
        changed = False
        if self._search_message_transient and self.search_message:
            self.search_message = ""
            self._search_message_transient = False
            changed = True
        if self.jump_message:
            self.jump_message = ""
            changed = True
        if self._passive_status_transient and self._passive_status:
            self._passive_status = ""
            self._passive_status_transient = False
            changed = True
        if changed:
            self.invalidate()

    def set_passive_status(self, message: str, transient: bool = True) -> None:
        """Show a small passive status message in the top bar"""
        self._passive_status = message
        self._passive_status_transient = transient and bool(message)
        self.invalidate()

    def _set_search_message(self, message: str, transient: bool = True) -> None:
        """Update the search status message and whether it auto-clears"""
        self.search_message = message
        self._search_message_transient = transient and bool(message)
        self.invalidate()

    def _clear_search_message(self) -> None:
        """Clear search status messages without touching history or focus"""
        self.search_message = ""
        self._search_message_transient = False

    def _set_jump_message(self, message: str) -> None:
        """Update the jump status message shown in the shared input bar chrome"""
        self.jump_message = message
        self.invalidate()

    def _clear_jump_message(self) -> None:
        """Clear jump status messages without touching the current query"""
        self.jump_message = ""

    def _get_current_mode_name(self) -> str:
        """Return the editor mode that currently owns the user's attention"""
        overlay = self._get_visible_overlay()
        if overlay == "quit":
            return self.get_text("editor_mode_quit", "quit")
        if overlay == "help":
            return self.get_text("editor_mode_help", "help")
        if self.issue_mode_active:
            return self.get_text("editor_mode_issue", "issue")
        if overlay == "error":
            return self.get_text("editor_mode_err", "error")
        if self.jump_visible:
            return self.get_text("editor_mode_jump", "jump")
        if self.search_visible:
            return self.get_text("editor_mode_search", "search")
        return self.get_text("editor_mode_normal", "normal")

    def _get_mode_text(self) -> str:
        """Render a compact mode strip for the top bar"""
        mode = self._get_current_mode_name()
        if mode == "issue":
            total = len(self._document_issue_cache)
            ordinal = min(self.issue_index + 1, total) if total else 0
            return (
                " "
                + self.format_text(
                    "editor_mode_issue_status",
                    "[issue {ordinal} of {total}]",
                    ordinal=ordinal,
                    total=total,
                )
                + " "
            )
        return f" [ {mode} ] "

    def _get_status_text(self) -> str:
        """Show passive status, issue counts, or validation pause feedback"""
        if self._passive_status:
            return f" {self._passive_status} "
        if not self.expensive_checks_enabled():
            return (
                " "
                + self.get_text("editor_status_checks_paused", "mention checks paused")
                + " "
            )
        issues = self.get_document_issues()
        if issues:
            return (
                " "
                + self.format_text(
                    "editor_status_issue_count",
                    "{count} {label}",
                    count=len(issues),
                    label=self.get_text(
                        "editor_issue_label_plural"
                        if len(issues) != 1
                        else "editor_issue_label_singular",
                        "issues" if len(issues) != 1 else "issue",
                    ),
                )
                + " "
            )
        return ""

    def _get_token_status_text(self) -> str:
        """Render token status with the requested busy-indicator format"""
        busy = self._token_estimate_busy or not self.expensive_checks_enabled()
        suffix = "* " if busy else "  "
        return f" ~{self.token_count} tokens{suffix}"

    def _get_toolbar_text(self) -> str:
        """Swap toolbar hints to match the current interaction mode"""
        mode = self._get_current_mode_name()
        if mode == "quit":
            return get_string("toolbar_text_quit", "[Y/Enter/] quit | [N/Esc] cancel")
        if mode == "search":
            return get_string(
                "toolbar_text_search",
                "[Enter] next | ^[R] replace | [Esc] close",
            )
        if mode == "jump":
            return get_string("toolbar_text_jump", "[Enter] jump | [Esc] close")
        if mode == "issue":
            return get_string(
                "toolbar_text_issue", "[N/Enter] next | ^[P/R] prev | [Esc] close"
            )
        if mode == "help":
            return get_string("toolbar_text_help", "[Esc/Enter] close")
        return get_string(
            "toolbar_text_normal",
            "^[G] help | ^[F] find | [Alt+G] jump | [Alt+Z] wrap",
        )

    def toggle_word_wrap(self) -> None:
        """Flip main editor wrapping at runtime and surface the new mode briefly"""
        self.word_wrap_enabled = not self.word_wrap_enabled
        self.main_window.wrap_lines = to_filter(self.word_wrap_enabled)
        self.set_passive_status(
            self.get_text(
                (
                    "editor_word_wrap_enabled"
                    if self.word_wrap_enabled
                    else "editor_word_wrap_disabled"
                ),
                "word wrap on" if self.word_wrap_enabled else "word wrap off",
            ),
            transient=True,
        )
        self.invalidate()

    def _remember_search_query(self, query: str) -> None:
        """Keep a small in-memory history of search queries"""
        query = query.strip()
        if not query:
            return
        self._search_history = [item for item in self._search_history if item != query]
        self._search_history.insert(0, query)
        del self._search_history[self.SEARCH_HISTORY_LIMIT :]
        self._search_history_index = -1

    def cycle_search_history(self, direction: int) -> None:
        """Move backward or forward through recent search queries"""
        if not self._search_history:
            return

        if self._search_history_index < 0:
            self._search_history_draft = self.search_buffer.text
            self._search_history_index = 0 if direction < 0 else -1
        else:
            self._search_history_index -= direction

        if self._search_history_index < 0:
            self._search_history_index = -1
            query = self._search_history_draft
        elif self._search_history_index >= len(self._search_history):
            self._search_history_index = len(self._search_history) - 1
            query = self._search_history[self._search_history_index]
        else:
            query = self._search_history[self._search_history_index]

        self._search_history_navigation_active = True
        try:
            self.search_buffer.document = Document(query, cursor_position=len(query))
        finally:
            self._search_history_navigation_active = False

    def _get_search_label_text(self) -> str:
        """Emphasize search mode with an always-visible header and count"""
        if not self.search_visible:
            return ""
        return " " + self.get_text("editor_search_label", "SEARCH") + " "

    def _get_replace_label_text(self) -> str:
        """Show the replace row label only while replace mode is open"""
        if not self.search_visible or not self.replace_visible:
            return ""
        return " " + self.get_text("editor_replace_label", "REPLACE") + " "

    def _append_toggle_fragment(
        self,
        fragments: StyleAndTextTuples,
        *,
        enabled: bool,
        enabled_text: str,
        disabled_text: str,
        leading_space: bool = True,
    ) -> None:
        """Append one styled toggle chip to a formatted-text fragment list"""
        if leading_space:
            fragments.append(("", " "))
        fragments.append(
            (
                "class:search-toggle-on" if enabled else "class:search-toggle-off",
                enabled_text if enabled else disabled_text,
            )
        )

    def _get_search_toggle_fragments(self) -> StyleAndTextTuples:
        """Render the visible search mode chips as styled fragments"""
        fragments: StyleAndTextTuples = []
        self._append_toggle_fragment(
            fragments,
            enabled=self.search_options.match_case,
            enabled_text=self.get_text("editor_search_toggle_case_on", "[Aa]"),
            disabled_text=self.get_text("editor_search_toggle_case_off", "(Aa)"),
            leading_space=False,
        )
        self._append_toggle_fragment(
            fragments,
            enabled=self.search_options.match_whole_word,
            enabled_text=self.get_text("editor_search_toggle_word_on", "[Ab]"),
            disabled_text=self.get_text("editor_search_toggle_word_off", "(Ab)"),
        )
        self._append_toggle_fragment(
            fragments,
            enabled=self.search_options.regex,
            enabled_text=self.get_text("editor_search_toggle_regex_on", "[.*]"),
            disabled_text=self.get_text("editor_search_toggle_regex_off", "(.*)"),
        )
        return fragments

    def _get_replace_toggle_fragments(self) -> StyleAndTextTuples:
        """Render the replace preserve-case chip as styled fragments"""
        fragments: StyleAndTextTuples = []
        self._append_toggle_fragment(
            fragments,
            enabled=self.search_options.preserve_case,
            enabled_text=self.get_text(
                "editor_replace_toggle_preserve_case_on", "[Preserve]"
            ),
            disabled_text=self.get_text(
                "editor_replace_toggle_preserve_case_off", "(Preserve)"
            ),
            leading_space=False,
        )
        return fragments

    def _join_status_fragments(
        self,
        left_text: str,
        right_fragments: StyleAndTextTuples | None = None,
    ) -> StyleAndTextTuples:
        """Combine plain status text with styled toggle chips for the widget"""
        fragments: StyleAndTextTuples = [("", " ")]
        if left_text:
            fragments.append(("", left_text))
        if right_fragments:
            if left_text:
                fragments.append(("", "  "))
            fragments.extend(right_fragments)
        fragments.append(("", " "))
        return fragments

    def _get_jump_label_text(self) -> str:
        """Render the jump bar label only while jump mode is visible"""
        if not self.jump_visible:
            return ""
        return " " + self.get_text("editor_jump_label", "JUMP") + " "

    def _get_jump_default_text(self) -> str:
        """Expose the current cursor location as the jump bar's inline suggestion"""
        return build_jump_target(
            self.buffer.document.cursor_position_row + 1,
            self.buffer.document.cursor_position_col + 1,
        )[1:]

    def _normalize_jump_target_text(self, text: str) -> str:
        """Normalize raw jump input into the mandatory-colon form used by parsing"""
        suffix = text.strip()
        if suffix.startswith(":"):
            suffix = suffix[1:]
        return ":" + suffix if suffix else ""

    async def _update_tokens_loop(self):
        """Update token counts asynchronously using debounced estimation"""
        last_text = None
        last_count = 0
        while True:
            await asyncio.sleep(self.TOKEN_UPDATE_INTERVAL)
            if self.result is not None:
                break

            if not self.expensive_checks_enabled():
                continue

            current_text = self.buffer.text
            if current_text != last_text:
                last_text = current_text
                self._token_estimate_busy = True
                self.invalidate()
                try:
                    new_count = await self.resolver.count_tokens(current_text)
                    if new_count != last_count:
                        self.token_count = new_count
                        last_count = new_count
                except Exception:
                    pass
                finally:
                    self._token_estimate_busy = False
                    self.invalidate()

    def _get_search_status_text(self) -> AnyFormattedText:
        """Return search mode hints or the last search result message"""
        state = self._get_search_highlight_state()
        toggles = self._get_search_toggle_fragments()
        if self.search_message:
            return self._join_status_fragments(self.search_message, toggles)
        if state and state.query:
            if not state.matches:
                return self._join_status_fragments(
                    self.format_text(
                        "editor_search_status_count",
                        "{current} of {total}",
                        current=0,
                        total=0,
                    ),
                    toggles,
                )
            return self._join_status_fragments(
                self.format_text(
                    "editor_search_status_count",
                    "{current} of {total}",
                    current=state.active_ordinal,
                    total=len(state.matches),
                ),
                toggles,
            )
        return self._join_status_fragments("", toggles)

    def _get_replace_status_text(self) -> AnyFormattedText:
        """Return replace-row status chips while replace is visible"""
        if not self.search_visible or not self.replace_visible:
            return ""
        return self._join_status_fragments("", self._get_replace_toggle_fragments())

    def _get_jump_status_text(self) -> str:
        """Return jump mode hints or validation feedback for the target input"""
        if self.jump_message:
            return f" {self.jump_message} "
        return ""

    def _handle_search_text_changed(self, _buffer: Buffer) -> None:
        """Clear stale search navigation state after query edits"""
        self._clear_search_message()
        self._reset_search_navigation()
        if not self._search_history_navigation_active:
            self._search_history_index = -1
        self.invalidate()

    def _handle_replace_text_changed(self, _buffer: Buffer) -> None:
        """Refresh the widget when replace content changes"""
        self.invalidate()

    def _handle_jump_text_changed(self, _buffer: Buffer) -> None:
        """Clear stale jump validation once the requested target changes"""
        self._clear_jump_message()
        self.invalidate()

    def _handle_buffer_text_changed(self, _buffer: Buffer) -> None:
        """Invalidate cached issue state and stale issue overlays after edits"""
        self._document_issue_cache_text_id = 0
        self._document_issue_cache = tuple()
        if self.issue_mode_active:
            self.deactivate_issue_mode()

    def _refresh_jump_suggestion(self) -> None:
        """Recompute the jump bar suggestion from the live main-editor cursor"""
        auto_suggest = self.jump_buffer.auto_suggest
        if auto_suggest is None:
            return
        self.jump_buffer.suggestion = auto_suggest.get_suggestion(
            self.jump_buffer,
            self.jump_buffer.document,
        )
        self.jump_buffer.on_suggestion_set.fire()

    def _invalidate_search_cache(self) -> None:
        """Drop cached search results after any search mode change"""
        self._search_cache_state = None
        self._search_cache_text_id = 0
        self._search_cache_cursor = -1
        self._search_cache_query = ""

    def _reset_search_navigation(self) -> None:
        """Clear the last explicit search step anchor"""
        self._search_last_query = ""
        self._search_last_direction = 1
        self._search_last_match = None
        self._invalidate_search_cache()

    def _set_search_option(self, name: str, value: bool) -> None:
        """Apply one search flag and clear stale search state"""
        if getattr(self.search_options, name) == value:
            return
        setattr(self.search_options, name, value)
        self._clear_search_message()
        self._reset_search_navigation()
        self.invalidate()

    def toggle_match_case(self) -> None:
        """Toggle case-sensitive search mode"""
        self._set_search_option("match_case", not self.search_options.match_case)

    def toggle_match_whole_word(self) -> None:
        """Toggle whole-word search mode"""
        self._set_search_option(
            "match_whole_word", not self.search_options.match_whole_word
        )

    def toggle_regex(self) -> None:
        """Toggle regex search mode"""
        self._set_search_option("regex", not self.search_options.regex)

    def toggle_preserve_case(self) -> None:
        """Toggle preserve-case replace mode"""
        self._set_search_option("preserve_case", not self.search_options.preserve_case)

    def _compile_search_pattern(self, query: str) -> re.Pattern[str] | None:
        """Compile the current search query into a reusable pattern"""
        if not query:
            return None
        body = query if self.search_options.regex else re.escape(query)
        if self.search_options.match_whole_word:
            body = rf"\b(?:{body})\b"
        flags = 0 if self.search_options.match_case else re.IGNORECASE
        return re.compile(body, flags)

    def _make_issue(
        self,
        line: int,
        column: int,
        end_column: int,
        style: str,
        message: str,
        fragment: str,
    ) -> EditorIssue:
        """Build a stable issue record for navigation and rendering"""
        return EditorIssue(line, column, end_column, style, message, fragment)

    def _make_line_match_issue(
        self,
        lineno: int,
        match: re.Match[str],
        style: str,
        message: str,
    ) -> EditorIssue:
        """Build an issue from a single-line regex match"""
        return self._make_issue(
            lineno,
            match.start(),
            match.end(),
            style,
            message,
            match.group(0),
        )

    def _make_buffer_match_issue(
        self,
        match: re.Match[str],
        style: str,
        message: str,
    ) -> EditorIssue:
        """Build an issue from a whole-buffer regex match"""
        start_line, start_col = self.buffer.document.translate_index_to_position(
            match.start()
        )
        end_col = start_col + (match.end() - match.start())
        return self._make_issue(
            start_line,
            start_col,
            end_col,
            style,
            message,
            match.group(0),
        )

    def get_document_issues(self) -> tuple[EditorIssue, ...]:
        """Collect lightweight syntax and reference issues from the buffer"""
        expensive_enabled = self.expensive_checks_enabled()
        text = self.buffer.text
        text_id = id(text)
        if (
            self._document_issue_cache_text_id == text_id
            and self._document_issue_cache_enabled == expensive_enabled
        ):
            return self._document_issue_cache

        issues: list[EditorIssue] = []
        document = self.buffer.document
        if self.lexer is not None:
            invalid_fence_lines = self.lexer.get_invalid_fence_lines(document)
            for lineno in sorted(invalid_fence_lines):
                line_text = document.lines[lineno]
                issues.append(
                    self._make_issue(
                        lineno,
                        0,
                        len(line_text),
                        "invalid-syntax",
                        self.get_text(
                            "issue_unclosed_code_fence",
                            "unclosed code fence",
                        ),
                        line_text,
                    )
                )

            for lineno, line in enumerate(document.lines):
                for match in self.lexer.mention_pattern.finditer(line):
                    fragment = match.group(0)
                    if expensive_enabled:
                        validation = self.lexer.inspect_mention(fragment)
                        if validation.style is None or validation.message is None:
                            continue
                        issues.append(
                            self._make_line_match_issue(
                                lineno,
                                match,
                                validation.style,
                                validation.message,
                            )
                        )
                    elif not fragment.endswith(">") and fragment != "[@project]":
                        issues.append(
                            self._make_line_match_issue(
                                lineno,
                                match,
                                "invalid-syntax",
                                self.get_text(
                                    "issue_incomplete_mention_syntax",
                                    "incomplete mention syntax",
                                ),
                            )
                        )

        self._document_issue_cache_text_id = text_id
        self._document_issue_cache_enabled = expensive_enabled
        self._document_issue_cache = tuple(issues)
        return self._document_issue_cache

    async def collect_save_issues(self) -> tuple[EditorIssue, ...]:
        """Run save-time issue checks, including symbol lookups"""
        issues = {
            (issue.line, issue.column, issue.end_column): issue
            for issue in self.get_document_issues()
        }
        text = self.buffer.text
        for match in re.finditer(r"<@symbol:([^>:]+):([^>]+)>", text):
            path, symbol = match.groups()
            file_matches = self.indexer.find_matches(path)
            issue = self._make_buffer_match_issue(
                match,
                "unresolved-reference",
                self.format_text(
                    "issue_symbol_file_unresolved",
                    "symbol file '{path}' could not be resolved",
                    path=path,
                ),
            )
            issue_key = (issue.line, issue.column, issue.end_column)

            if not file_matches:
                issues[issue_key] = issue
                continue

            meta = file_matches[0]
            try:
                from ..core.extractor import SymbolExtractor
                import aiofiles

                async with aiofiles.open(
                    meta.path, "r", encoding="utf-8", errors="replace"
                ) as handle:
                    content = await handle.read()

                extractor = SymbolExtractor(content, meta.path.name)
                if not extractor.extract(symbol):
                    raise ValueError(
                        self.format_text(
                            "issue_symbol_not_found",
                            "symbol '{symbol}' not found",
                            symbol=symbol,
                        )
                    )
            except Exception as err:
                issues[issue_key] = self._make_buffer_match_issue(
                    match,
                    issue.style,
                    self.format_text(
                        "issue_symbol_resolution_err",
                        "{path}: {err}",
                        path=meta.rel_path,
                        e=err,
                    ),
                )

        return tuple(
            sorted(issues.values(), key=lambda issue: (issue.line, issue.column))
        )

    def _get_search_highlight_state(self) -> SearchHighlightState | None:
        """Return a cached search snapshot to avoid repeated full scans"""
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
            and self._search_cache_options == self.search_options
        ):
            return self._search_cache_state

        if not query:
            state = SearchHighlightState("", tuple(), None, 0)
        else:
            try:
                pattern = self._compile_search_pattern(query)
            except re.error as err:
                self._set_search_message(str(err))
                state = SearchHighlightState(query, tuple(), None, 0)
                self._search_cache_text_id = text_id
                self._search_cache_cursor = cursor
                self._search_cache_query = query
                self._search_cache_options = self.search_options.copy()
                self._search_cache_state = state
                return state

            matches = (
                tuple(
                    SearchMatch(match.start(), match.end())
                    for match in pattern.finditer(text)
                    if match.start() != match.end()
                )
                if pattern is not None
                else tuple()
            )

            active_match: SearchMatch | None = None
            active_ordinal = 0
            if matches:
                cursor_match = next(
                    (match for match in matches if match.start <= cursor < match.end),
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
                        (match for match in matches if match.start >= cursor),
                        matches[0],
                    )

                active_ordinal = matches.index(active_match) + 1

            state = SearchHighlightState(query, matches, active_match, active_ordinal)

        self._search_cache_text_id = text_id
        self._search_cache_cursor = cursor
        self._search_cache_query = query
        self._search_cache_options = self.search_options.copy()
        self._search_cache_state = state
        return state

    def _focus_search(self) -> None:
        """Move input focus into the search field if an app is active"""
        self._focus_target("search")

    def _focus_replace(self) -> None:
        """Move input focus into the replace field if replace is visible"""
        self._focus_target("replace")

    def _focus_main(self) -> None:
        """Restore input focus to the main editor buffer"""
        self._focus_target("main")

    def open_search(self) -> None:
        """Show the search bar and prepare it for immediate input"""
        self.note_user_activity()
        self.jump_visible = False
        self.jump_buffer.document = Document("", cursor_position=0)
        self._clear_jump_message()
        self.search_visible = True
        self._clear_search_message()
        self._invalidate_search_cache()
        if self.search_buffer.text:
            self.search_buffer.cursor_position = len(self.search_buffer.text)
        elif self._search_history:
            query = self._search_history[0]
            self.search_buffer.document = Document(query, cursor_position=len(query))
        self._focus_search()

    def close_search(self) -> None:
        """Hide the search bar and return focus to the editor"""
        self.search_visible = False
        self.replace_visible = False
        self._clear_search_message()
        self._reset_search_navigation()
        self._focus_target("main")

    def toggle_replace(self) -> None:
        """Toggle the replace row beneath the active search field"""
        self.open_search()
        self.replace_visible = not self.replace_visible
        if not self.replace_visible:
            self._focus_search()
            return
        self._focus_replace()

    def open_jump(self) -> None:
        """Show the jump bar and prepare it for a line or line:column target"""
        self.note_user_activity()
        self.search_visible = False
        self.replace_visible = False
        self._clear_search_message()
        self._reset_search_navigation()
        self.jump_visible = True
        self.jump_buffer.document = Document("", cursor_position=0)
        self._clear_jump_message()
        self._refresh_jump_suggestion()
        self._focus_target("jump")
        self.invalidate()

    def close_jump(self) -> None:
        """Hide the jump bar and return focus to the editor"""
        self.jump_visible = False
        self.jump_buffer.document = Document("", cursor_position=0)
        self._clear_jump_message()
        self._focus_target("main")

    def submit_jump(self) -> bool:
        """Jump to the requested line and optional character position"""
        raw_target = self._normalize_jump_target_text(self.jump_buffer.text)
        if not raw_target:
            raw_target = build_jump_target(
                self.buffer.document.cursor_position_row + 1,
                self.buffer.document.cursor_position_col + 1,
            )

        parsed = parse_jump_target(raw_target)
        if parsed is None:
            self._set_jump_message(
                self.get_text(
                    "editor_jump_invalid_format",
                    "use :line[:char] or :line,char",
                )
            )
            return False

        line, column = parsed
        document = self.buffer.document
        if line < 1 or line > document.line_count:
            self._set_jump_message(
                self.get_text("editor_jump_line_out_of_range", "line out of range")
            )
            return False

        line_text = document.lines[line - 1]
        max_column = len(line_text) + 1
        if column < 1 or column > max_column:
            self._set_jump_message(
                self.get_text(
                    "editor_jump_char_out_of_range",
                    "character out of range",
                )
            )
            return False

        self.buffer.cursor_position = document.translate_row_col_to_index(
            line - 1,
            column - 1,
        )
        self._search_cache_state = None
        self.close_jump()
        self.invalidate()
        return True

    def open_help(self) -> None:
        """Show the help overlay and focus it"""
        self._show_overlay("help", preserve_view=True)
        if self.search_visible and self._help_search_anchor >= 0:
            self._set_help_cursor(self._help_search_anchor)
        elif self.issue_mode_active and self._help_issue_anchor >= 0:
            self._set_help_cursor(self._help_issue_anchor)
        else:
            self._set_help_cursor(0)
        self._focus_target("help")
        self.invalidate()

    def close_help(self) -> None:
        """Hide the help overlay and return focus to the active edit target"""
        self._hide_overlay("help", restore_view=True)
        self.invalidate()

    def toggle_help(self) -> None:
        """Toggle help visibility without losing the active search context"""
        if self.help_visible:
            self.close_help()
        else:
            self.open_help()

    def open_quit_confirm(self) -> None:
        """Show a confirmation modal before aborting the editor session"""
        self.note_user_activity()
        self._show_overlay("quit")
        self.quit_buffer.cursor_position = 0
        self._focus_target("quit")
        self.invalidate()

    def close_quit_confirm(self) -> None:
        """Dismiss the quit modal and restore focus to the previous target"""
        self._hide_overlay("quit")
        self.invalidate()

    def confirm_quit(self) -> None:
        """Abort the current editor session without saving"""
        self._set_overlay_visible("quit", False)
        self.result = None
        self.invalidate()

    def _find_search_match(
        self, matches: tuple[SearchMatch, ...], start: int, direction: int
    ) -> tuple[SearchMatch | None, bool]:
        """Search forward or backward across precomputed match spans"""
        if not matches:
            return None, False
        if direction > 0:
            for match in matches:
                if match.start >= start:
                    return match, False
            return matches[0], True

        for match in reversed(matches):
            if match.start <= start:
                return match, False
        return matches[-1], True

    def search_step(self, direction: int) -> bool:
        """Move to the next or previous search match while keeping search open"""
        query = self.search_buffer.text
        if not query:
            self._set_search_message(
                self.get_text("editor_search_enter_query", "enter a query")
            )
            return False

        try:
            state = self._get_search_highlight_state()
        except re.error as err:
            self._set_search_message(str(err))
            return False

        if state is None or not state.matches:
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return False

        repeated = (
            query == self._search_last_query
            and direction == self._search_last_direction
            and self._search_last_match is not None
            and self.buffer.cursor_position == self._search_last_match.start
        )
        start = self.buffer.cursor_position
        if direction > 0 and repeated and self._search_last_match is not None:
            start = self._search_last_match.end
        elif direction < 0:
            start -= 1

        match, wrapped = self._find_search_match(state.matches, start, direction)
        if match is None:
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return False

        self.buffer.cursor_position = match.start
        self._search_last_query = query
        self._search_last_direction = direction
        self._search_last_match = match
        self._invalidate_search_cache()
        self._remember_search_query(query)
        self._set_search_message(
            self.get_text("editor_search_wrapped", "wrapped") if wrapped else "",
            transient=wrapped,
        )
        return True

    def replace_current(self) -> bool:
        """Replace the active match and keep the replace widget open"""
        state = self._get_search_highlight_state()
        if state is None or not state.matches:
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return False

        match = state.active_match or state.matches[0]
        text = self.buffer.text
        source = text[match.start : match.end]
        replacement = self._expand_replacement(source, match)
        self.buffer.text = text[: match.start] + replacement + text[match.end :]
        self.buffer.cursor_position = match.start + len(replacement)
        self._remember_search_query(self.search_buffer.text)
        self._clear_search_message()
        self._reset_search_navigation()
        self.invalidate()
        return True

    def replace_all(self) -> int:
        """Replace every current match and return the replacement count"""
        query = self.search_buffer.text
        if not query:
            self._set_search_message(
                self.get_text("editor_search_enter_query", "enter a query")
            )
            return 0

        text = self.buffer.text
        try:
            pattern = self._compile_search_pattern(query)
        except re.error as err:
            self._set_search_message(str(err))
            return 0
        if pattern is None:
            return 0

        def _replace(match: re.Match[str]) -> str:
            source = match.group(0)
            replacement = (
                match.expand(self.replace_buffer.text)
                if self.search_options.regex
                else self.replace_buffer.text
            )
            if self.search_options.preserve_case:
                replacement = _preserve_replacement_case(source, replacement)
            return replacement

        new_text, count = pattern.subn(_replace, text)
        if count <= 0:
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return 0

        self.buffer.text = new_text
        self.buffer.cursor_position = 0
        self._remember_search_query(query)
        self._clear_search_message()
        self._reset_search_navigation()
        self.invalidate()
        return count

    def _expand_replacement(self, source: str, match: SearchMatch) -> str:
        """Build the replacement text for one concrete match span"""
        replacement = self.replace_buffer.text
        if self.search_options.regex:
            pattern = self._compile_search_pattern(self.search_buffer.text)
            if pattern is not None:
                match_obj = pattern.search(self.buffer.text, match.start, match.end)
                if match_obj is not None:
                    replacement = match_obj.expand(replacement)
        if self.search_options.preserve_case:
            replacement = _preserve_replacement_case(source, replacement)
        return replacement

    def activate_issue_mode(self, issues: tuple[EditorIssue, ...]) -> None:
        """Enter issue mode, jump to the first issue, and show the overlay"""
        self.issue_mode_active = bool(issues)
        self._document_issue_cache = issues
        self.issue_index = 0
        if issues:
            self.jump_to_issue(0)
            self._render_issue_overlay()

    def deactivate_issue_mode(self) -> None:
        """Exit issue mode and dismiss the overlay"""
        self.issue_mode_active = False
        self._hide_overlay("error")
        self.err_message = ""
        self.invalidate()

    def _render_issue_overlay(self) -> None:
        """Update the existing overlay window with the active issue details"""
        if not self.issue_mode_active or not self._document_issue_cache:
            return
        issue = self._document_issue_cache[self.issue_index]
        total = len(self._document_issue_cache)
        title = self.get_text(
            "editor_issue_title_syntax"
            if issue.style == "invalid-syntax"
            else "editor_issue_title_reference",
            "syntax" if issue.style == "invalid-syntax" else "reference",
        )
        self._show_overlay("error")
        self.err_message = issue.message
        self.err_buffer.set_document(
            Document(
                self.format_text(
                    "editor_issue_overlay",
                    "{title} issue at :{line}:{column}...\n\n{message}\n\n{fragment}\n{context_label}\n\nissue {ordinal} of {total}\n{controls}\n",
                    title=title,
                    ordinal=self.issue_index + 1,
                    total=total,
                    line=issue.line + 1,
                    column=issue.column + 1,
                    message=issue.message,
                    context_label=self.get_text("editor_issue_context_label", "^^^^"),
                    fragment=issue.fragment,
                    controls=self.get_text(
                        "editor_issue_controls",
                        "[Enter/N] next  ^[R/P] prev  [Esc] close",
                    ),
                ),
                cursor_position=0,
            ),
            bypass_readonly=True,
        )
        self._focus_target("error")
        self.invalidate()

    def jump_to_issue(self, index: int) -> None:
        """Move the main cursor to the target issue and keep it in view"""
        if not self._document_issue_cache:
            return
        self.issue_index = index % len(self._document_issue_cache)
        issue = self._document_issue_cache[self.issue_index]
        self.buffer.cursor_position = self.buffer.document.translate_row_col_to_index(
            issue.line, issue.column
        )
        self._search_cache_state = None
        self.invalidate()

    def _get_err_title_text(self) -> str:
        """Return a compact title for error and issue overlays"""
        if self.issue_mode_active and self._document_issue_cache:
            total = len(self._document_issue_cache)
            ordinal = min(self.issue_index + 1, total)
            return (
                " < "
                + self.format_text(
                    "editor_issue_title_bar",
                    "issues [{ordinal}/{total}]",
                    ordinal=ordinal,
                    total=total,
                )
                + " > "
            )
        return " < " + get_string("err_title", "error") + " > "

    def step_issue(self, direction: int) -> bool:
        """Move to the next or previous issue while issue mode is active"""
        if not self.issue_mode_active or not self._document_issue_cache:
            return False
        self.jump_to_issue(self.issue_index + direction)
        self._render_issue_overlay()
        return True

    async def run_async(self) -> str | None:
        """Run the full-screen editor"""
        default_bindings = load_key_bindings()
        custom_bindings = setup_keybindings(self)
        bindings = merge_key_bindings([default_bindings, custom_bindings])

        top_bar = VSplit(
            [
                Window(
                    content=FormattedTextControl(self._get_mode_text),
                    style="class:topbar-mode",
                    width=Dimension(preferred=20),
                ),
                Window(
                    content=FormattedTextControl(
                        lambda: (
                            " < " + self.get_text("editor_title", "promptify") + " > "
                        )
                    ),
                    style="class:topbar-title",
                    align=WindowAlign.CENTER,
                    width=Dimension(weight=1),
                ),
                Window(
                    content=FormattedTextControl(self._get_status_text),
                    style="class:topbar-status",
                    align=WindowAlign.RIGHT,
                    width=Dimension(preferred=24),
                ),
                Window(
                    content=FormattedTextControl(self._get_token_status_text),
                    style="class:topbar-tokens",
                    align=WindowAlign.RIGHT,
                    width=Dimension(preferred=18),
                ),
            ],
            height=1,
            style="class:topbar",
        )

        bottom_toolbar = VSplit(
            [
                Window(
                    content=FormattedTextControl(
                        lambda: " " + self._get_toolbar_text() + " "
                    ),
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

        editor_frame = self._build_chrome(self.main_window, "", "class:editor-frame")

        body = HSplit(
            [
                top_bar,
                editor_frame,
                ConditionalContainer(
                    content=self.search_window,
                    filter=Condition(lambda: self.search_visible),
                ),
                ConditionalContainer(
                    content=self.jump_window,
                    filter=Condition(lambda: self.jump_visible),
                ),
                bottom_toolbar,
            ]
        )

        help_float = self._build_modal_float(
            self.help_window,
            " < " + get_string("help_title", "help") + " > ",
            "class:help-frame",
            Condition(lambda: self.help_visible),
        )

        err_float = self._build_modal_float(
            self.err_window,
            self._get_err_title_text,
            "class:err-frame",
            Condition(lambda: self.err_visible),
        )

        quit_float = self._build_modal_float(
            self.quit_window,
            " < " + get_string("quit_title", "quit") + " > ",
            "class:err-frame",
            Condition(lambda: self.quit_visible),
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
                    help_float,
                    err_float,
                    quit_float,
                ],
            )
        )

        style = self._build_style()

        app = Application(
            layout=layout,
            key_bindings=bindings,
            style=style,
            erase_when_done=True,
            full_screen=(
                APP_SETTINGS.editor_layout.full_screen
                and self.terminal_profile.supports_full_screen
            ),
            mouse_support=(
                APP_SETTINGS.editor_layout.mouse_support
                and self.terminal_profile.supports_mouse
            ),
        )
        app.ttimeoutlen = APP_SETTINGS.editor_layout.ttimeoutlen

        self._focus_target(self._get_focus_target())

        token_task = asyncio.create_task(self._update_tokens_loop())
        try:
            await app.run_async()
        finally:
            token_task.cancel()
            with suppress(asyncio.CancelledError):
                await token_task
            self._token_estimate_busy = False

        return self.result

    def expensive_checks_enabled(self) -> bool:
        """Skip redraw-time validation while a bulk edit is still settling"""
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            return True
        return now >= self._bulk_mode_until

    def should_complete_while_typing(self) -> bool:
        """Run fuzzy completion only when the cursor is inside an active mention"""
        if not self.expensive_checks_enabled():
            return False
        return self.should_complete(self.buffer.document)

    def should_complete(self, document: Document) -> bool:
        """Gate autocomplete so normal prose and pastes do not trigger fuzzy search"""
        tail = document.text_before_cursor[-256:]
        return bool(re.search(r"(<@[^>\n]*)|(\[@[^\]\n]*)$", tail))

    def start_bulk_edit(self, inserted_text: str) -> None:
        """Temporarily relax completion and validation after large pastes"""
        if len(inserted_text) < self.BULK_EDIT_SIZE_THRESHOLD:
            return

        loop = asyncio.get_running_loop()
        self._bulk_mode_until = max(
            self._bulk_mode_until, loop.time() + self.BULK_EDIT_SUSPEND_SECONDS
        )
        self.invalidate()

        async def _refresh_after_pause():
            await asyncio.sleep(self.BULK_EDIT_SUSPEND_SECONDS)
            try:
                app = get_app()
            except Exception:
                return
            app.invalidate()

        asyncio.create_task(_refresh_after_pause())

    def paste_text(self, buffer: Buffer, text: str) -> None:
        """Apply pasted text through the fast bulk-edit path"""
        if not text:
            return

        buffer.save_to_undo_stack()

        if buffer.selection_state:
            buffer.cut_selection()
            buffer.selection_state = None

        self.start_bulk_edit(text)
        buffer.insert_text(text)

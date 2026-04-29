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
    from prompt_toolkit.selection import SelectionState
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


def _flatten_fragments_to_chars(
    fragments: StyleAndTextTuples,
) -> list[tuple[str, str]]:
    """FLATTENS FRAGMENTS INTO STYLE/CHARACTER PAIRS FOR RANGE-SAFE REWRITES."""
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
    """RESTORES A STYLE-PRESERVING TOKEN SLICE FROM FLATTENED CHARACTER DATA."""
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
    log.warning(
        get_string(
            "err_pygments_missing",
            "'pygments' library is missing. syntax highlighting will be disabled. install it using: 'uv pip install pygments'",
        )
    )

try:
    from rapidfuzz import process  # NOQA: F401
except ImportError:
    log.error(
        get_string(
            "err_rapidfuzz_missing",
            "'rapidfuzz' library is missing. install it using: 'uv pip install rapidfuzz'",
        )
    )
    sys.exit(1)


MENTION_SCAN_PATTERN = r"<@(?:\\.|[^>\n])+(?:>|$)|\[@[^\]\n]*(?:\]|$)"
HELP_TOKEN_PATTERN = r"(<@(?:\\.|[^>\n])+>|\[@project\])|(\^?\[[^\]\n]+\])"
HELP_TEXT_FALLBACK = (
    "[ general ]\n\n"
    "^[G] / [F1]                   : help\n"
    "^[F]                          : search\n"
    "^[S]                          : resolve\n"
    "^[Q]                          : abort\n\n"
    "[ search ]\n\n"
    "[Enter]                       : next\n"
    "^[R]                          : previous\n"
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
class SearchHighlightState:
    """CACHED SEARCH SNAPSHOT FOR HIGHLIGHTING AND STATUS RENDERING."""

    query: str
    matches: tuple[int, ...]
    active_match: int | None
    active_ordinal: int


@dataclass(frozen=True)
class MentionValidationResult:
    """CAPTURES WHETHER A MENTION IS VALID, MALFORMED, OR UNRESOLVED."""

    style: str | None
    message: str | None


@dataclass(frozen=True)
class EditorIssue:
    """REPRESENTS A NAVIGABLE EDITOR ISSUE IN THE CURRENT DOCUMENT."""

    line: int
    column: int
    end_column: int
    style: str
    message: str
    fragment: str


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


class ActiveLineProcessor(Processor):
    """HIGHLIGHTS THE ACTIVE EDITOR ROW WITHOUT ALTERING THE DOCUMENT TEXT."""

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
            self.mention_pattern = re.compile(MENTION_SCAN_PATTERN)
            self._validation_cache: dict[tuple[int, str], MentionValidationResult] = {}
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

        def _cache_validation_result(
            self,
            cache_key: tuple[int, str],
            style: str | None,
            message: str | None,
        ) -> MentionValidationResult:
            """STORES AND RETURNS A VALIDATION RESULT IN ONE STEP."""
            result = MentionValidationResult(style, message)
            self._validation_cache[cache_key] = result
            return result

        def _validate_safe_path(
            self,
            path: str,
            label: str = "path",
        ) -> MentionValidationResult | None:
            """REPORTS PATHS THAT ESCAPE THE PROJECT ROOT."""
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
            """VALIDATES THAT A QUERY PATH IS SAFE AND RESOLVES TO A FILE."""
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
            """CLASSIFIES A MENTION AS VALID, MALFORMED, OR UNRESOLVED."""
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
            """BACKWARD-COMPATIBILITY HELPER FOR BOOLEAN VALIDATION CALLERS."""
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
    """ROBUST REGEX-BASED LEXER FOR THE HELP WINDOW TEXT."""

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
        """TRIMS AND PADDS A SINGLE COMPLETION COLUMN CONSISTENTLY."""
        text, text_width = self._trim_formatted_text_left(content, width - trim_delta)
        padding = " " * max(0, width - padding_delta - text_width)

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

        return self._get_trimmed_column_fragments(
            to_formatted_text(completion.display_meta),
            style_str,
            width,
            trim_delta=2,
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
        self._help_restore_focus = "main"
        self._help_restore_main_cursor = 0
        self._help_restore_search_cursor = 0
        self._help_restore_main_selection: SelectionState | None = None
        self._help_restore_search_selection: SelectionState | None = None
        self._document_issue_cache_text_id = 0
        self._document_issue_cache_enabled = True
        self._document_issue_cache: tuple[EditorIssue, ...] = tuple()
        self.issue_mode_active = False
        self.issue_index = 0

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

        self.error_visible = False
        self.error_message = ""
        self.error_buffer = Buffer(document=Document(""), read_only=True)
        self.error_window = Window(
            content=BufferControl(buffer=self.error_buffer),
            style="class:error-text",
            wrap_lines=True,
            width=Dimension(
                min=APP_SETTINGS.editor_layout.error_width_min,
                max=APP_SETTINGS.editor_layout.error_width_max,
                weight=1,
            ),
            height=Dimension(
                min=APP_SETTINGS.editor_layout.error_height_min,
                max=APP_SETTINGS.editor_layout.error_height_max,
                weight=1,
            ),
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
                    content=FormattedTextControl(self._get_search_label_text),
                    style="class:search-label",
                    width=Dimension(preferred=18),
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
        )
        self.completions_menu = ResponsiveCompletionsMenu(
            max_height=self.COMPLETION_MENU_MAX_HEIGHT,
            scroll_offset=self.COMPLETION_MENU_SCROLL_OFFSET,
        )

    def _build_style(self) -> Style:
        """BUILDS THE EDITOR STYLE MAP AND FALLS BACK IF CONFIG VALUES ARE INVALID."""
        try:
            return Style.from_dict(APP_SETTINGS.theme.styles)
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
                    "search-match": "bg:#5d4a1d #fff0cb",
                    "search-match-active": "bg:#1f5d8e #f7fbff bold",
                    "current-line": "bg:#262a31",
                    "error-frame": "bg:#101317",
                    "error-frame.border": "fg:#768394",
                    "error-frame.label": "bg:#101317 #d7e6f6 bold",
                    "error-text": "bg:#171c22 #f2f5f8",
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
                }
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

    def _build_chrome(self, body, title, style: str):
        """BUILDS RESIZE-SAFE CHROME USING ASCII OR UNICODE BORDER GLYPHS."""
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
        """BUILDS A FULL-VIEWPORT CENTERED MODAL FLOAT AROUND RESIZE-SAFE CHROME."""
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
        """CLONES A SELECTION SNAPSHOT SO HELP OVERLAYS CAN RESTORE IT CLEANLY."""
        if selection_state is None:
            return None
        return SelectionState(
            original_cursor_position=selection_state.original_cursor_position,
            type=selection_state.type,
        )

    def _restore_selection_state(
        self, buffer: Buffer, selection_state: SelectionState | None
    ) -> None:
        """REAPPLIES A SAVED SELECTION SNAPSHOT TO A TARGET BUFFER."""
        buffer.selection_state = self._copy_selection_state(selection_state)

    def _focus(self, target) -> None:
        """FOCUSES A TARGET IF AN APPLICATION IS ACTIVE."""
        try:
            get_app().layout.focus(target)
        except Exception:
            pass

    def invalidate(self) -> None:
        """REQUESTS A REDRAW WHEN AN APPLICATION IS ACTIVE."""
        try:
            app = get_app()
        except Exception:
            return
        if app:
            app.invalidate()

    def get_text(self, key: str, default: str) -> str:
        """READS A LOCALIZED UI STRING WITH AN INLINE FALLBACK."""
        return get_string(key, default)

    def format_text(self, key: str, default: str, /, **values: object) -> str:
        """READS AND FORMATS A LOCALIZED UI STRING WITH INLINE FALLBACKS."""
        return self.get_text(key, default).format(**values)

    def _set_help_cursor(self, position: int) -> None:
        """MOVES THE HELP BUFFER CURSOR WITHOUT REACHING THROUGH UNTYPED CONTROLS."""
        self.help_buffer.cursor_position = position

    def note_user_activity(self) -> None:
        """CLEARS TRANSIENT STATUS MESSAGES AFTER THE NEXT USER ACTION."""
        changed = False
        if self._search_message_transient and self.search_message:
            self.search_message = ""
            self._search_message_transient = False
            changed = True
        if self._passive_status_transient and self._passive_status:
            self._passive_status = ""
            self._passive_status_transient = False
            changed = True
        if changed:
            self.invalidate()

    def set_passive_status(self, message: str, transient: bool = True) -> None:
        """SHOWS A SMALL, PASSIVE STATUS MESSAGE IN THE TOP BAR."""
        self._passive_status = message
        self._passive_status_transient = transient and bool(message)
        self.invalidate()

    def _set_search_message(self, message: str, transient: bool = True) -> None:
        """UPDATES THE SEARCH STATUS MESSAGE AND WHETHER IT AUTO-CLEARS."""
        self.search_message = message
        self._search_message_transient = transient and bool(message)
        self.invalidate()

    def _clear_search_message(self) -> None:
        """CLEARS SEARCH STATUS MESSAGES WITHOUT TOUCHING HISTORY OR FOCUS."""
        self.search_message = ""
        self._search_message_transient = False

    def _reset_search_navigation(self) -> None:
        """CLEARS CACHED SEARCH NAVIGATION STATE AFTER QUERY OR MODE CHANGES."""
        self._search_last_query = ""
        self._search_last_direction = 1
        self._search_last_match = -1
        self._search_cache_state = None

    def _get_current_mode_name(self) -> str:
        """RETURNS THE EDITOR MODE CURRENTLY OWNING THE USER'S ATTENTION."""
        if self.help_visible:
            return self.get_text("editor_mode_help", "help")
        if self.issue_mode_active:
            return self.get_text("editor_mode_issue", "issue")
        if self.error_visible:
            return self.get_text("editor_mode_error", "error")
        if self.search_visible:
            return self.get_text("editor_mode_search", "search")
        return self.get_text("editor_mode_normal", "normal")

    def _get_mode_text(self) -> str:
        """RENDERS A COMPACT MODE STRIP FOR THE TOP BAR."""
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
        """SHOWS PASSIVE STATUS, ISSUE COUNTS, OR VALIDATION PAUSE FEEDBACK."""
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
        """RENDERS TOKEN STATUS WITH THE REQUESTED BUSY INDICATOR FORMAT."""
        busy = self._token_estimate_busy or not self.expensive_checks_enabled()
        suffix = "* " if busy else "  "
        return f" ~{self.token_count} tokens{suffix}"

    def _get_toolbar_text(self) -> str:
        """SWAPS TOOLBAR HINTS TO MATCH THE CURRENT INTERACTION MODE."""
        mode = self._get_current_mode_name()
        if mode == "search":
            return get_string("toolbar_text_search", "")
        if mode == "issue":
            return get_string("toolbar_text_issue", "")
        if mode == "help":
            return get_string("toolbar_text_help", "")
        return get_string("toolbar_text_normal", "")

    def _remember_search_query(self, query: str) -> None:
        """KEEPS A SMALL IN-MEMORY SESSION HISTORY OF SEARCH QUERIES."""
        query = query.strip()
        if not query:
            return
        self._search_history = [item for item in self._search_history if item != query]
        self._search_history.insert(0, query)
        del self._search_history[self.SEARCH_HISTORY_LIMIT :]
        self._search_history_index = -1

    def _cycle_search_history(self) -> None:
        """ROTATES THROUGH RECENT SEARCH QUERIES WHEN SEARCH IS ALREADY OPEN."""
        if not self._search_history:
            return
        next_index = (self._search_history_index + 1) % len(self._search_history)
        if (
            self.search_buffer.text
            and len(self._search_history) > 1
            and self._search_history[next_index] == self.search_buffer.text
        ):
            next_index = (next_index + 1) % len(self._search_history)
        self._search_history_index = next_index
        query = self._search_history[self._search_history_index]
        self.search_buffer.document = Document(query, cursor_position=len(query))

    def _get_search_label_text(self) -> str:
        """EMPHASIZES SEARCH MODE WITH AN ALWAYS-VISIBLE HEADER AND COUNT."""
        if not self.search_visible:
            return ""
        return " " + self.get_text("editor_search_label", "SEARCH") + " "

    async def _update_tokens_loop(self):
        """ASYNCHRONOUS, DEBOUNCED TASK UTILIZING FAST PROXY METRICS FOR TOKEN SIZE."""
        last_text = None
        last_count = 0
        while True:
            await asyncio.sleep(self.TOKEN_UPDATE_INTERVAL)
            if self.result is not None:
                break

            current_text = self.buffer.text
            if current_text != last_text:
                last_text = current_text
                self._token_estimate_busy = True
                self.invalidate()
                try:
                    new_count = await self.resolver.estimate_tokens(current_text)
                    if new_count != last_count:
                        self.token_count = new_count
                        last_count = new_count
                except Exception:
                    pass
                finally:
                    self._token_estimate_busy = False
                    self.invalidate()

    def _get_search_status_text(self) -> str:
        """RETURNS SEARCH MODE HINTS OR THE LAST SEARCH RESULT MESSAGE."""
        state = self._get_search_highlight_state()
        if self.search_message:
            return f" {self.search_message} "
        if state and state.query:
            if not state.matches:
                return (
                    " "
                    + self.format_text(
                        "editor_search_status_count",
                        "{current} of {total}",
                        current=0,
                        total=0,
                    )
                    + " "
                )
            return (
                " "
                + self.format_text(
                    "editor_search_status_count",
                    "{current} of {total}",
                    current=state.active_ordinal,
                    total=len(state.matches),
                )
                + " "
            )
        return ""

    def _handle_search_text_changed(self, _buffer: Buffer) -> None:
        """CLEARS STALE SEARCH NAVIGATION STATE AFTER QUERY EDITS."""
        self._clear_search_message()
        self._reset_search_navigation()
        self._search_history_index = -1
        self.invalidate()

    def _handle_buffer_text_changed(self, _buffer: Buffer) -> None:
        """INVALIDATES CACHED ISSUE STATE AND STALE ISSUE OVERLAYS AFTER EDITS."""
        self._document_issue_cache_text_id = 0
        self._document_issue_cache = tuple()
        if self.issue_mode_active:
            self.deactivate_issue_mode()

    def _make_issue(
        self,
        line: int,
        column: int,
        end_column: int,
        style: str,
        message: str,
        fragment: str,
    ) -> EditorIssue:
        """BUILDS A STABLE ISSUE RECORD FOR NAVIGATION AND RENDERING."""
        return EditorIssue(line, column, end_column, style, message, fragment)

    def _make_line_match_issue(
        self,
        lineno: int,
        match: re.Match[str],
        style: str,
        message: str,
    ) -> EditorIssue:
        """BUILDS AN ISSUE FROM A SINGLE-LINE REGEX MATCH."""
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
        """BUILDS AN ISSUE FROM A WHOLE-BUFFER REGEX MATCH."""
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
        """COLLECTS LIGHTWEIGHT SYNTAX AND REFERENCE ISSUES FROM THE BUFFER."""
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
        """RUNS SAVE-TIME ISSUE CHECKS, INCLUDING SYMBOL LOOKUPS."""
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
            except Exception as error:
                issues[issue_key] = self._make_buffer_match_issue(
                    match,
                    issue.style,
                    self.format_text(
                        "issue_symbol_resolution_error",
                        "{path}: {error}",
                        path=meta.rel_path,
                        error=error,
                    ),
                )

        return tuple(
            sorted(issues.values(), key=lambda issue: (issue.line, issue.column))
        )

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
        self._focus(self.search_buffer)

    def _focus_main(self) -> None:
        """RESTORES INPUT FOCUS TO THE MAIN EDITOR BUFFER."""
        self._focus(self.main_window)

    def open_search(self) -> None:
        """SHOWS THE SEARCH BAR AND PREPARES IT FOR IMMEDIATE INPUT."""
        self.note_user_activity()
        self.search_visible = True
        self._clear_search_message()
        self._search_cache_state = None
        if self.search_buffer.text:
            self._cycle_search_history()
        elif self._search_history:
            query = self._search_history[0]
            self.search_buffer.document = Document(query, cursor_position=len(query))
        self.search_buffer.cursor_position = len(self.search_buffer.text)
        self._focus_search()

    def close_search(self) -> None:
        """HIDES THE SEARCH BAR AND RETURNS FOCUS TO THE EDITOR."""
        self.search_visible = False
        self._clear_search_message()
        self._reset_search_navigation()
        self._focus_main()

    def open_help(self) -> None:
        """SHOWS THE HELP OVERLAY AND FOCUSES IT."""
        self._help_restore_focus = (
            "search"
            if self.search_visible
            else "error"
            if self.error_visible
            else "main"
        )
        self._help_restore_main_cursor = self.buffer.cursor_position
        self._help_restore_search_cursor = self.search_buffer.cursor_position
        self._help_restore_main_selection = self._copy_selection_state(
            self.buffer.selection_state
        )
        self._help_restore_search_selection = self._copy_selection_state(
            self.search_buffer.selection_state
        )
        self.help_visible = True
        if self.search_visible and self._help_search_anchor >= 0:
            self._set_help_cursor(self._help_search_anchor)
        elif self.issue_mode_active and self._help_issue_anchor >= 0:
            self._set_help_cursor(self._help_issue_anchor)
        else:
            self._set_help_cursor(0)
        self._focus(self.help_window)

    def close_help(self) -> None:
        """HIDES THE HELP OVERLAY AND RETURNS FOCUS TO THE ACTIVE EDIT TARGET."""
        self.help_visible = False
        self.buffer.cursor_position = self._help_restore_main_cursor
        self.search_buffer.cursor_position = self._help_restore_search_cursor
        self._restore_selection_state(self.buffer, self._help_restore_main_selection)
        self._restore_selection_state(
            self.search_buffer, self._help_restore_search_selection
        )
        if self._help_restore_focus == "search" and self.search_visible:
            self._focus_search()
        elif self._help_restore_focus == "error" and self.error_visible:
            self._focus(self.error_window)
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
            self._set_search_message(
                self.get_text("editor_search_enter_query", "enter a query")
            )
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
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return False

        self.buffer.cursor_position = match_pos
        self._search_last_query = query
        self._search_last_direction = direction
        self._search_last_match = match_pos
        self._search_cache_state = None
        self._remember_search_query(query)
        self._set_search_message(
            self.get_text("editor_search_wrapped", "wrapped") if wrapped else "",
            transient=wrapped,
        )
        return True

    def activate_issue_mode(self, issues: tuple[EditorIssue, ...]) -> None:
        """ENTERS ISSUE MODE, JUMPS TO THE FIRST ISSUE, AND SHOWS THE OVERLAY."""
        self.issue_mode_active = bool(issues)
        self._document_issue_cache = issues
        self.issue_index = 0
        if issues:
            self.jump_to_issue(0)
            self._render_issue_overlay()

    def deactivate_issue_mode(self) -> None:
        """EXITS ISSUE MODE AND DISMISSES THE OVERLAY."""
        self.issue_mode_active = False
        self.error_visible = False
        self.error_message = ""
        self._focus_main()
        self.invalidate()

    def _render_issue_overlay(self) -> None:
        """UPDATES THE EXISTING OVERLAY WINDOW WITH THE ACTIVE ISSUE DETAILS."""
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
        self.error_visible = True
        self.error_message = issue.message
        self.error_buffer.set_document(
            Document(
                self.format_text(
                    "editor_issue_overlay",
                    "{title} issue {ordinal} of {total}\nline {line}, col {column}\n\n{message}\n\n{context_label}\n{fragment}\n\n{controls}",
                    title=title,
                    ordinal=self.issue_index + 1,
                    total=total,
                    line=issue.line + 1,
                    column=issue.column + 1,
                    message=issue.message,
                    context_label=self.get_text(
                        "editor_issue_context_label", "context"
                    ),
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
        self._focus(self.error_window)
        self.invalidate()

    def jump_to_issue(self, index: int) -> None:
        """MOVES THE MAIN CURSOR TO THE TARGET ISSUE AND KEEPS IT IN VIEW."""
        if not self._document_issue_cache:
            return
        self.issue_index = index % len(self._document_issue_cache)
        issue = self._document_issue_cache[self.issue_index]
        self.buffer.cursor_position = self.buffer.document.translate_row_col_to_index(
            issue.line, issue.column
        )
        self._search_cache_state = None
        self.invalidate()

    def _get_error_title_text(self) -> str:
        """RETURNS A COMPACT, RESPONSIVE TITLE FOR ERROR AND ISSUE OVERLAYS."""
        if self.issue_mode_active and self._document_issue_cache:
            total = len(self._document_issue_cache)
            ordinal = min(self.issue_index + 1, total)
            return (
                " < "
                + self.format_text(
                    "editor_issue_title_bar",
                    "issues {ordinal} / {total}",
                    ordinal=ordinal,
                    total=total,
                )
                + " > "
            )
        return " < " + get_string("error_title", "error") + " > "

    def step_issue(self, direction: int) -> bool:
        """MOVES TO THE NEXT OR PREVIOUS ISSUE WHILE ISSUE MODE IS ACTIVE."""
        if not self.issue_mode_active or not self._document_issue_cache:
            return False
        self.jump_to_issue(self.issue_index + direction)
        self._render_issue_overlay()
        return True

    async def run_async(self) -> str | None:
        """EXECUTES THE FULL SCREEN EDITOR."""
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
                bottom_toolbar,
            ]
        )

        help_float = self._build_modal_float(
            self.help_window,
            " < " + get_string("help_title", "help") + " > ",
            "class:help-frame",
            Condition(lambda: self.help_visible),
        )

        error_float = self._build_modal_float(
            self.error_window,
            self._get_error_title_text,
            "class:error-frame",
            Condition(lambda: self.error_visible),
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
                    error_float,
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
        """APPLIES PASTED TEXT THROUGH THE FAST BULK-EDIT PATH."""
        if not text:
            return

        buffer.save_to_undo_stack()

        if buffer.selection_state:
            buffer.cut_selection()
            buffer.selection_state = None

        self.start_bulk_edit(text)
        buffer.insert_text(text)

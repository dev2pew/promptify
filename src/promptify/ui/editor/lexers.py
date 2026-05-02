"""Lexers and mention tokenization for the interactive editor."""

from __future__ import annotations

import re
from typing import Callable, cast

from ...core.indexer import ProjectIndexer
from ...core.mods import (
    ModRegistry,
    parse_git_mention_query,
    split_file_query_and_range,
    split_git_branch_prefix,
)
from ...core.resolver import PromptResolver
from ...shared.editor_state import MentionValidationResult
from ...shared.editor_support import (
    HELP_TOKEN_PATTERN,
    MENTION_SCAN_PATTERN,
    append_original_token_range,
    flatten_fragments_to_chars,
)
from ...utils.i18n import get_string
from ._imports import (
    Document,
    HAS_PYGMENTS,
    Lexer,
    MarkdownLexer,
    PygmentsLexer,
    StyleAndTextTuples,
)


def tokenize_mention(text: str) -> list[tuple[str, str]]:
    """Tokenize mentions with semantic parsing for their arguments."""
    if text == "[@project]":
        return [("class:mention-tag", "[@project]")]
    if not (text.startswith("<@") and text.endswith(">")):
        return [("class:mention-tag", text)]

    inner = text[2:-1]
    if ":" not in inner:
        return [("class:mention-tag", text)]

    tag_type, rest = inner.split(":", 1)
    tokens = [("class:mention-tag", f"<@{tag_type}")]

    def add_sep() -> None:
        tokens.append(("", ":"))

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
                    "class:mention-path" if command == "diff" else "class:mention-range"
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
        match = re.match(r"^([^>]+?)(?::([^>:]+))?$", rest)
        if match:
            path, arg2 = match.groups()
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
                else:
                    tokens.append(("class:mention-range", arg2))
        else:
            add_sep()
            tokens.append(("class:mention-path", rest))
    elif tag_type in ("ext", "type"):
        add_sep()
        tokens.append(("class:mention-ext", rest))
    else:
        add_sep()
        tokens.append(("class:mention-path", rest))

    tokens.append(("class:mention-tag", ">"))
    return tokens


class CustomPromptLexer(Lexer):
    """Custom lexer for tag highlighting and invalid-mention detection."""

    def __init__(
        self,
        registry: ModRegistry,
        indexer: ProjectIndexer,
        resolver: PromptResolver,
        expensive_checks_enabled: Callable[[], bool] | None = None,
    ):
        if not HAS_PYGMENTS or PygmentsLexer is None or MarkdownLexer is None:
            raise RuntimeError("CustomPromptLexer requires pygments")
        self.md_lexer = PygmentsLexer(MarkdownLexer)
        self.registry = registry
        self.indexer = indexer
        self.resolver = resolver
        self.expensive_checks_enabled = expensive_checks_enabled or (lambda: True)
        self.mention_pattern = re.compile(MENTION_SCAN_PATTERN)
        self._validation_cache: dict[tuple[int, str], MentionValidationResult] = {}
        self._invalid_fence_cache: dict[int, set[int]] = {}

    def get_invalid_fence_lines(self, document: Document) -> set[int]:
        """Flag only the last unmatched fence line to avoid noisy highlighting."""
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
        """Store and return a validation result in one step."""
        result = MentionValidationResult(style, message)
        self._validation_cache[cache_key] = result
        return result

    def _validate_safe_path(
        self,
        path: str,
        label: str = "path",
    ) -> MentionValidationResult | None:
        """Report paths that escape the project root."""
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
        """Validate that a query path is safe and resolves to a file."""
        path_issue = self._validate_safe_path(path)
        if path_issue is not None:
            if unsafe_message is not None:
                return MentionValidationResult(path_issue.style, unsafe_message)
            return path_issue
        if not self.indexer.find_matches(path):
            return MentionValidationResult(
                "unresolved-reference",
                missing_message,
            )
        return None

    def inspect_mention(self, text: str) -> MentionValidationResult:
        """Classify a mention as valid, malformed, or unresolved."""
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
                path_match = re.match(r"<@(dir|tree):([^>:]+)", text)
                if path_match:
                    clean = path_match.group(2).replace("\\", "/").strip("/")
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
                symbol_match = re.match(r"<@symbol:([^>:]+?)(?::([^>]+))?>", text)
                if not symbol_match:
                    return self._cache_validation_result(
                        cache_key,
                        "invalid-syntax",
                        get_string(
                            "issue_malformed_symbol_mention",
                            "malformed symbol mention",
                        ),
                    )
                path = symbol_match.group(1)
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
                ext_match = re.match(r"<@(type|ext):([^>]+)>", text)
                if not ext_match:
                    return self._cache_validation_result(
                        cache_key,
                        "invalid-syntax",
                        get_string(
                            "issue_malformed_extension_mention",
                            "malformed extension mention",
                        ),
                    )
                exts = [item.strip().lower() for item in ext_match.group(2).split(",")]
                if not self.indexer.get_by_extensions(exts):
                    return self._cache_validation_result(
                        cache_key,
                        "unresolved-reference",
                        get_string(
                            "issue_extensions_unresolved",
                            "no files found for extensions '{extensions}'",
                        ).format(extensions=ext_match.group(2)),
                    )
            return self._cache_validation_result(cache_key, None, None)
        except Exception:
            return self._cache_validation_result(
                cache_key,
                "invalid-syntax",
                get_string("issue_failed_to_parse_mention", "failed to parse mention"),
            )

    def is_valid_mention(self, text: str) -> bool:
        """Backward-compatibility helper for boolean validation callers."""
        return self.inspect_mention(text).style is None

    def lex_document(self, document: Document):
        get_original_line = self.md_lexer.lex_document(document)
        invalid_fence_lines = self.get_invalid_fence_lines(document)

        def get_line(lineno: int) -> StyleAndTextTuples:
            original_tokens = get_original_line(lineno)
            text = document.lines[lineno]
            matches = list(self.mention_pattern.finditer(text))
            if not matches:
                if lineno in invalid_fence_lines:
                    return [("class:invalid-syntax", text)]
                return original_tokens

            chars = flatten_fragments_to_chars(original_tokens)
            new_tokens: list[tuple[object, ...]] = []
            last_idx = 0
            for match in matches:
                start, end = match.span()
                mention_text = match.group(0)
                append_original_token_range(new_tokens, chars, last_idx, start)
                if not self.expensive_checks_enabled():
                    new_tokens.extend(tokenize_mention(mention_text))
                else:
                    validation = self.inspect_mention(mention_text)
                    if validation.style is None:
                        new_tokens.extend(tokenize_mention(mention_text))
                    else:
                        new_tokens.append((f"class:{validation.style}", mention_text))
                last_idx = end

            append_original_token_range(new_tokens, chars, last_idx, len(chars))
            if lineno in invalid_fence_lines:
                return [("class:invalid-syntax", text)]
            return cast(StyleAndTextTuples, new_tokens)

        return get_line


class HelpLexer(Lexer):
    """Regex-based lexer for help window text."""

    def __init__(self):
        self.header_re = re.compile(r"^\s*\[ .* \]\s*$")
        self.combined_re = re.compile(HELP_TOKEN_PATTERN)

    def lex_document(self, document: Document):
        def get_line(lineno: int) -> StyleAndTextTuples:
            text = document.lines[lineno]
            if self.header_re.match(text):
                return [("class:help-header", text)]

            tokens: list[tuple[object, ...]] = []
            last_idx = 0
            for match in self.combined_re.finditer(text):
                start = match.start()
                if start > last_idx:
                    tokens.append(("", text[last_idx:start]))

                mention, key = match.groups()
                if mention:
                    tokens.extend(tokenize_mention(mention))
                else:
                    tokens.append(("class:help-key", key))
                last_idx = match.end()

            if last_idx < len(text):
                tokens.append(("", text[last_idx:]))
            return cast(StyleAndTextTuples, tokens)

        return get_line

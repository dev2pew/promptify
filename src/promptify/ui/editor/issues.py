"""Issue collection and issue-overlay mixin for the interactive editor"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from ...core.indexer import ProjectIndexer
from ...shared.editor_state import (
    EditorIssue,
    FocusTarget,
    OverlayName,
    SearchHighlightState,
)
from ...utils.i18n import get_string
from ._imports import Buffer, Document
from .lexers import CustomPromptLexer


class EditorIssuesMixin:
    """Provide document issue collection plus issue-mode navigation"""

    issue_mode_active: bool = False
    issue_index: int = 0
    _document_issue_cache_text_id: int = 0
    _document_issue_cache_enabled: bool = True
    _document_issue_cache: tuple[EditorIssue, ...] = ()
    _search_cache_state: SearchHighlightState | None = None
    buffer: Buffer = cast(Buffer, cast(object, None))
    lexer: CustomPromptLexer | None = None
    indexer: ProjectIndexer = cast(ProjectIndexer, cast(object, None))
    err_message: str = ""
    err_buffer: Buffer = cast(Buffer, cast(object, None))

    if TYPE_CHECKING:

        def expensive_checks_enabled(self) -> bool:
            raise NotImplementedError

        def get_text(self, key: str, default: str) -> str:
            _ = key, default
            raise NotImplementedError

        def format_text(self, key: str, default: str, /, **values: object) -> str:
            _ = key, default, values
            raise NotImplementedError

        def invalidate(self) -> None:
            raise NotImplementedError

        def _hide_overlay(
            self, overlay: OverlayName, *, restore_view: bool = False
        ) -> None:
            _ = overlay, restore_view
            raise NotImplementedError

        def _show_overlay(
            self,
            overlay: OverlayName,
            *,
            restore_focus: FocusTarget | None = None,
            preserve_view: bool = False,
        ) -> OverlayName:
            _ = overlay, restore_focus, preserve_view
            raise NotImplementedError

        def _focus_target(self, target: FocusTarget) -> None:
            _ = target
            raise NotImplementedError

    def _handle_buffer_text_changed(self, _buffer: Buffer) -> None:
        """Invalidate cached issue state and stale issue overlays after edits"""
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
                import aiofiles

                from ...core.extractor import SymbolExtractor

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
                        err=err,
                    ),
                )

        return tuple(
            sorted(issues.values(), key=lambda issue: (issue.line, issue.column))
        )

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
        _ = self._show_overlay("error")
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

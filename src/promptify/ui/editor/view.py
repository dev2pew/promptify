"""View-building and status-rendering mixin for the interactive editor"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, cast

import promptify.core.settings as settings_module

from ...core.terminal import TerminalProfile
from ...shared.editor_state import (
    EditorIssue,
    OverlayName,
    SearchHighlightState,
    SearchOptions,
)
from ...shared.editor_support import build_jump_target
from ...utils.i18n import get_string
from ..suggestions import AUTO_SUGGESTION_STYLE
from ._imports import (
    AnyContainer,
    AnyFormattedText,
    Buffer,
    BufferControl,
    Condition,
    ConditionalContainer,
    Dimension,
    Float,
    FormattedTextControl,
    HSplit,
    Processor,
    Style,
    StyleAndTextTuples,
    VSplit,
    Window,
    WindowAlign,
    to_filter,
)


class EditorViewMixin:
    """Provide shared view builders, status text, and small UI helpers"""

    terminal_profile: TerminalProfile = cast(TerminalProfile, cast(object, None))
    token_count: int = 0
    word_wrap_enabled: bool = False
    search_visible: bool = False
    replace_visible: bool = False
    jump_visible: bool = False
    help_visible: bool = False
    issue_mode_active: bool = False
    issue_index: int = 0
    search_options: SearchOptions = SearchOptions()
    search_message: str = ""
    jump_message: str = ""
    _search_message_transient: bool = False
    _passive_status: str = ""
    _passive_status_transient: bool = False
    _token_estimate_busy: bool = False
    _document_issue_cache: tuple[EditorIssue, ...] = ()
    buffer: Buffer = cast(Buffer, cast(object, None))
    search_buffer: Buffer = cast(Buffer, cast(object, None))
    replace_buffer: Buffer = cast(Buffer, cast(object, None))
    jump_buffer: Buffer = cast(Buffer, cast(object, None))
    help_buffer: Buffer = cast(Buffer, cast(object, None))
    main_window: Window = cast(Window, cast(object, None))

    if TYPE_CHECKING:

        def invalidate(self) -> None: ...

        def expensive_checks_enabled(self) -> bool: ...

        def get_document_issues(self) -> tuple[EditorIssue, ...]: ...

        def _get_visible_overlay(self) -> OverlayName: ...

        def _get_search_highlight_state(self) -> SearchHighlightState | None: ...

    def _build_input_bar(
        self,
        buffer: Buffer,
        get_label_text: Callable[[], str],
        get_status_text: Callable[[], AnyFormattedText],
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
            styles = dict(settings_module.APP_SETTINGS.theme.styles)
            _ = styles.setdefault("auto-suggestion", AUTO_SUGGESTION_STYLE)
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
                    "multi-cursor": "bg:#d7f6ff #101317 bold",
                    "multi-cursor-selection": "bg:#244a60 #eef9ff",
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
        self, container: AnyContainer, visible_filter: Condition
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

    def _build_chrome(
        self,
        body: AnyContainer,
        title: str | Callable[[], str],
        style: str,
    ) -> HSplit:
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
                    Window(width=1, height=1, char=border.top_left, style=border_style),
                    Window(
                        width=1, height=1, char=border.horizontal, style=border_style
                    ),
                    Window(content=title_control, style=label_style, height=1),
                    Window(
                        width=1, height=1, char=border.horizontal, style=border_style
                    ),
                    Window(
                        width=1, height=1, char=border.top_right, style=border_style
                    ),
                ],
                height=1,
            )
            if has_title
            else VSplit(
                [
                    Window(width=1, height=1, char=border.top_left, style=border_style),
                    Window(height=1, char=border.horizontal, style=border_style),
                    Window(
                        width=1, height=1, char=border.top_right, style=border_style
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
        body: AnyContainer,
        title: str | Callable[[], str],
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

    def _build_top_bar(self) -> VSplit:
        """Build the top mode, title, status, and token strip"""
        return VSplit(
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

    def _build_bottom_toolbar(self) -> VSplit:
        """Build the bottom toolbar and live cursor location strip"""
        return VSplit(
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

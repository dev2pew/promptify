"""Interactive editor runtime class and app assembly."""

from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from typing import final, override

import promptify.core.settings as settings_module
import promptify.core.terminal as terminal_module

from ...core.indexer import ProjectIndexer
from ...core.resolver import PromptResolver
from ...core.terminal import TerminalProfile
from ...shared.editor_state import (
    EditorIssue,
    EditorViewState,
    FocusTarget,
    OverlayName,
    SearchHighlightState,
    SearchMatch,
    SearchOptions,
)
from ...shared.editor_support import HELP_TEXT_FALLBACK
from ...utils.i18n import get_string
from ..bindings import setup_keybindings
from ..suggestions import PrefixSuggestion
from ._imports import (
    Application,
    AppendAutoSuggestion,
    BeforeInput,
    Buffer,
    BufferControl,
    Condition,
    ConditionalContainer,
    Dimension,
    Document,
    Float,
    FloatContainer,
    HSplit,
    HighlightMatchingBracketProcessor,
    Layout,
    NumberedMargin,
    Window,
    HAS_PYGMENTS,
    load_key_bindings,
    merge_key_bindings,
    to_filter,
    Processor,
    get_app,
)
from .completion import MentionCompleter, ResponsiveCompletionsMenu
from .issues import EditorIssuesMixin
from .lexers import CustomPromptLexer, HelpLexer
from .overlays import EditorOverlayMixin
from .processors import (
    ActiveLineProcessor,
    EOFNewlineProcessor,
    HighlightTrailingWhitespaceProcessor,
    SearchMatchProcessor,
    VerticalSeparatorMargin,
)
from .search import EditorSearchMixin
from .view import EditorViewMixin


@final
class InteractiveEditor(
    EditorIssuesMixin,
    EditorSearchMixin,
    EditorOverlayMixin,
    EditorViewMixin,
):
    """Manage the core prompt-toolkit terminal editor."""

    def __init__(
        self,
        initial_text: str,
        indexer: ProjectIndexer,
        resolver: PromptResolver,
        show_help: bool | None = None,
        terminal_profile: TerminalProfile | None = None,
    ):
        settings = settings_module.APP_SETTINGS
        if show_help is None:
            show_help = settings.editor_behavior.show_help_on_start
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
        self.terminal_profile = terminal_profile or terminal_module.APP_TERMINAL_PROFILE
        self.indexer = indexer
        self.resolver = resolver
        self.token_count = 0
        self.BULK_EDIT_SUSPEND_SECONDS = (
            settings.editor_behavior.bulk_edit_suspend_seconds
        )
        self.BULK_EDIT_SIZE_THRESHOLD = (
            settings.editor_behavior.bulk_edit_size_threshold
        )
        self.COMPLETION_MENU_MAX_HEIGHT = (
            settings.editor_layout.completion_menu_max_height
        )
        self.COMPLETION_MENU_SCROLL_OFFSET = (
            settings.editor_layout.completion_menu_scroll_offset
        )
        self.SEARCH_HISTORY_LIMIT = settings.editor_behavior.search_history_limit
        self.TOKEN_UPDATE_INTERVAL = settings.editor_behavior.token_update_interval
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
        self.word_wrap_enabled = settings.editor_behavior.word_wrap
        self.search_options = SearchOptions()

        self.buffer = Buffer(
            document=Document(initial_text, cursor_position=0),
            completer=MentionCompleter(
                indexer,
                resolver.registry,
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
                min=settings.editor_layout.help_width_min,
                max=settings.editor_layout.help_width_max,
                weight=1,
            ),
            height=Dimension(
                min=settings.editor_layout.help_height_min,
                max=settings.editor_layout.help_height_max,
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
                min=settings.editor_layout.err_width_min,
                max=settings.editor_layout.err_width_max,
                weight=1,
            ),
            height=Dimension(
                min=settings.editor_layout.err_height_min,
                max=settings.editor_layout.err_height_max,
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
                min=settings.editor_layout.err_width_min,
                max=settings.editor_layout.err_width_max,
                weight=1,
            ),
            height=Dimension(
                min=settings.editor_layout.err_height_min,
                max=settings.editor_layout.err_height_max,
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
                resolver.registry,
                indexer,
                resolver,
                self.expensive_checks_enabled,
            )
            if HAS_PYGMENTS
            else None
        )
        processors: list[Processor] = [
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
                if settings.editor_behavior.show_line_numbers
                else []
            ),
        )
        self.completions_menu = ResponsiveCompletionsMenu(
            max_height=self.COMPLETION_MENU_MAX_HEIGHT,
            scroll_offset=self.COMPLETION_MENU_SCROLL_OFFSET,
        )

    async def _update_tokens_loop(self) -> None:
        """Update token counts asynchronously using debounced estimation."""
        last_text: str | None = None
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

    async def run_async(self) -> str | None:
        """Run the full-screen editor."""
        settings = settings_module.APP_SETTINGS
        default_bindings = load_key_bindings()
        custom_bindings = setup_keybindings(self)
        bindings = merge_key_bindings([default_bindings, custom_bindings])

        editor_frame = self._build_chrome(self.main_window, "", "class:editor-frame")
        body = HSplit(
            [
                self._build_top_bar(),
                editor_frame,
                ConditionalContainer(
                    content=self.search_window,
                    filter=Condition(lambda: self.search_visible),
                ),
                ConditionalContainer(
                    content=self.jump_window,
                    filter=Condition(lambda: self.jump_visible),
                ),
                self._build_bottom_toolbar(),
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
                    Float(xcursor=True, ycursor=True, content=self.completions_menu),
                    help_float,
                    err_float,
                    quit_float,
                ],
            )
        )
        style = self._build_style()
        app: Application[None] = Application(
            layout=layout,
            key_bindings=bindings,
            style=style,
            erase_when_done=True,
            full_screen=(
                settings.editor_layout.full_screen
                and self.terminal_profile.supports_full_screen
            ),
            mouse_support=(
                settings.editor_layout.mouse_support
                and self.terminal_profile.supports_mouse
            ),
        )
        app.ttimeoutlen = settings.editor_layout.ttimeoutlen
        self._focus_target(self._get_focus_target())

        token_task = asyncio.create_task(self._update_tokens_loop())
        try:
            _ = await app.run_async()
        finally:
            _ = token_task.cancel()
            with suppress(asyncio.CancelledError):
                _ = await token_task
            self._token_estimate_busy = False

        return self.result

    @override
    def expensive_checks_enabled(self) -> bool:
        """Skip redraw-time validation while a bulk edit is still settling."""
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            return True
        return now >= self._bulk_mode_until

    def should_complete_while_typing(self) -> bool:
        """Run fuzzy completion only when the cursor is inside an active mention."""
        if not self.expensive_checks_enabled():
            return False
        return self.should_complete(self.buffer.document)

    def should_complete(self, document: Document) -> bool:
        """Gate autocomplete so normal prose and pastes do not trigger fuzzy search."""
        tail = document.text_before_cursor[-256:]
        return bool(re.search(r"(<@[^>\n]*)|(\[@[^\]\n]*)$", tail))

    def start_bulk_edit(self, inserted_text: str) -> None:
        """Temporarily relax completion and validation after large pastes."""
        if len(inserted_text) < self.BULK_EDIT_SIZE_THRESHOLD:
            return
        loop = asyncio.get_running_loop()
        self._bulk_mode_until = max(
            self._bulk_mode_until, loop.time() + self.BULK_EDIT_SUSPEND_SECONDS
        )
        self.invalidate()

        async def _refresh_after_pause() -> None:
            await asyncio.sleep(self.BULK_EDIT_SUSPEND_SECONDS)
            try:
                app = get_app()
            except Exception:
                return
            app.invalidate()

        _ = asyncio.create_task(_refresh_after_pause())

    def paste_text(self, buffer: Buffer, text: str) -> None:
        """Apply pasted text through the fast bulk-edit path."""
        if not text:
            return
        buffer.save_to_undo_stack()
        if buffer.selection_state:
            _ = buffer.cut_selection()
            buffer.selection_state = None
        self.start_bulk_edit(text)
        buffer.insert_text(text)

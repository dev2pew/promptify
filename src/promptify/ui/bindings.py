"""Keybinding registration for standard and custom editor shortcuts"""

import asyncio

import pyperclip
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, has_focus
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.selection import SelectionState

from .keybinding.context import EditorBindingContext
from .keybinding.dialogs import register_dialog_bindings
from .keybinding.editing import register_editing_bindings


def detect_indent_style(document: Document) -> str:
    """Detect the indentation style used in the current document"""
    for line in document.lines:
        if line.startswith("\t"):
            return "\t"
        if line.startswith("  ") and not line.startswith("   "):
            return "  "
        if line.startswith("    "):
            return "    "
    return "    "


def setup_keybindings(editor) -> KeyBindings:
    """Register the complete interactive-editor keymap"""
    custom_bindings = KeyBindings()

    @Condition
    def is_help_visible() -> bool:
        return editor.help_visible

    @Condition
    def is_err_visible() -> bool:
        return editor.err_visible

    @Condition
    def is_issue_mode_active() -> bool:
        return editor.issue_mode_active and editor.err_visible

    @Condition
    def is_quit_visible() -> bool:
        return editor.quit_visible

    @Condition
    def is_replace_visible() -> bool:
        return editor.replace_visible

    @Condition
    def has_completions_menu() -> bool:
        b = get_app().current_buffer
        return b.complete_state is not None and len(b.complete_state.completions) > 0

    @Condition
    def is_completion_selected() -> bool:
        b = get_app().current_buffer
        return (
            b.complete_state is not None
            and b.complete_state.current_completion is not None
        )

    editor_focus = has_focus(editor.buffer)
    search_focus = has_focus(editor.search_buffer)
    replace_focus = has_focus(editor.replace_buffer)
    jump_focus = has_focus(editor.jump_buffer)
    search_widget_focus = search_focus | replace_focus
    text_focus = editor_focus | search_focus | replace_focus | jump_focus

    def get_home_position(document: Document) -> int:
        first_non_ws = document.get_start_of_line_position(after_whitespace=True)
        if first_non_ws == 0:
            return document.get_start_of_line_position(after_whitespace=False)
        return first_non_ws

    def _start_sel(b: Buffer) -> None:
        if b.selection_state is None:
            b.selection_state = SelectionState(
                original_cursor_position=b.cursor_position
            )

    def _schedule_system_clipboard_paste() -> None:
        b = get_app().current_buffer

        async def _do_paste():
            try:
                text = await asyncio.to_thread(pyperclip.paste)
            except Exception:
                editor.set_passive_status(
                    editor.get_text("clipboard_unavailable", "clipboard unavailable")
                )
                return

            if text:
                editor.paste_text(b, text)
                get_app().invalidate()

        asyncio.create_task(_do_paste())

    ctx = EditorBindingContext(
        editor=editor,
        bindings=custom_bindings,
        editor_focus=editor_focus,
        search_focus=search_focus,
        replace_focus=replace_focus,
        jump_focus=jump_focus,
        search_widget_focus=search_widget_focus,
        text_focus=text_focus,
        is_help_visible=is_help_visible,
        is_err_visible=is_err_visible,
        is_issue_mode_active=is_issue_mode_active,
        is_quit_visible=is_quit_visible,
        is_replace_visible=is_replace_visible,
        has_completions_menu=has_completions_menu,
        is_completion_selected=is_completion_selected,
        detect_indent_style=detect_indent_style,
        get_home_position=get_home_position,
        start_selection=_start_sel,
        schedule_system_clipboard_paste=_schedule_system_clipboard_paste,
    )
    register_dialog_bindings(ctx)
    register_editing_bindings(ctx)

    return custom_bindings

"""Overlay, search, jump, and completion bindings for the interactive editor"""

from __future__ import annotations

from .context import EditorBindingContext


def register_dialog_bindings(ctx: EditorBindingContext) -> None:
    """Register editor bindings that manage overlays, search, and completions"""

    @ctx.bind("f1", note_activity=True)
    @ctx.bind("c-g", note_activity=True)
    def _toggle_help(event) -> None:
        ctx.editor.toggle_help()

    @ctx.bind("c-f", filter=ctx.text_focus, eager=True)
    def _search(event) -> None:
        """Open the custom search bar without entering prompt-toolkit search mode"""
        ctx.editor.open_search()

    @ctx.bind(
        "c-r",
        filter=ctx.editor_focus | ctx.search_widget_focus,
        eager=True,
        note_activity=True,
    )
    def _replace(event) -> None:
        """Toggle the replace row from the editor or search widget"""
        ctx.editor.toggle_replace()

    @ctx.bind("escape", "g", filter=ctx.text_focus, eager=True)
    def _jump(event) -> None:
        """Open the custom jump bar without colliding with built-in bindings"""
        ctx.editor.open_jump()

    @ctx.bind("escape", "z", filter=ctx.editor_focus, eager=True, note_activity=True)
    def _toggle_word_wrap(event) -> None:
        """Toggle runtime wrapping without colliding with undo"""
        ctx.editor.toggle_word_wrap()

    @ctx.bind(
        "escape",
        filter=ctx.is_help_visible & ~ctx.is_quit_visible,
        note_activity=True,
    )
    @ctx.bind(
        "enter",
        filter=ctx.is_help_visible & ~ctx.is_quit_visible,
        note_activity=True,
    )
    def _close_help(event) -> None:
        ctx.editor.close_help()

    @ctx.bind(
        "escape",
        filter=ctx.is_err_visible & ~ctx.is_quit_visible,
        note_activity=True,
        invalidate=True,
    )
    def _close_err(event) -> None:
        if ctx.editor.issue_mode_active:
            ctx.editor.deactivate_issue_mode()
        else:
            ctx.editor._hide_overlay("error")

    @ctx.bind("enter", filter=ctx.is_issue_mode_active, note_activity=True)
    @ctx.bind("c-n", filter=ctx.is_issue_mode_active, note_activity=True)
    def _next_issue(event) -> None:
        ctx.editor.step_issue(1)

    @ctx.bind("c-r", filter=ctx.is_issue_mode_active, note_activity=True)
    @ctx.bind("c-p", filter=ctx.is_issue_mode_active, note_activity=True)
    def _previous_issue(event) -> None:
        ctx.editor.step_issue(-1)

    @ctx.bind(
        "enter",
        filter=ctx.is_err_visible & ~ctx.is_issue_mode_active & ~ctx.is_quit_visible,
        note_activity=True,
        invalidate=True,
    )
    def _dismiss_err(event) -> None:
        ctx.editor._hide_overlay("error")

    @ctx.bind("enter", filter=ctx.is_quit_visible, note_activity=True)
    @ctx.bind("y", filter=ctx.is_quit_visible, note_activity=True)
    @ctx.bind("c-q", filter=ctx.is_quit_visible, note_activity=True)
    @ctx.bind("f10", filter=ctx.is_quit_visible, note_activity=True)
    def _confirm_quit(event) -> None:
        ctx.editor.confirm_quit()
        event.app.exit()

    @ctx.bind("escape", filter=ctx.is_quit_visible, note_activity=True)
    @ctx.bind("n", filter=ctx.is_quit_visible, note_activity=True)
    def _cancel_quit(event) -> None:
        ctx.editor.close_quit_confirm()

    @ctx.bind("up", filter=ctx.editor_focus & ctx.has_completions_menu)
    def _up_completion(event) -> None:
        event.current_buffer.complete_previous()

    @ctx.bind("down", filter=ctx.editor_focus & ctx.has_completions_menu)
    def _down_completion(event) -> None:
        event.current_buffer.complete_next()

    @ctx.bind(
        "enter",
        filter=ctx.editor_focus
        & ctx.has_completions_menu
        & ~ctx.is_completion_selected,
    )
    def _accept_first_completion(event) -> None:
        buffer = event.current_buffer
        if buffer.complete_state and buffer.complete_state.completions:
            buffer.apply_completion(buffer.complete_state.completions[0])

    @ctx.bind(
        "enter",
        filter=ctx.editor_focus & ctx.has_completions_menu & ctx.is_completion_selected,
    )
    def _accept_selected_completion(event) -> None:
        buffer = event.current_buffer
        if buffer.complete_state and buffer.complete_state.current_completion:
            buffer.apply_completion(buffer.complete_state.current_completion)

    @ctx.bind("escape", filter=ctx.editor_focus & ctx.has_completions_menu)
    def _cancel_completion(event) -> None:
        event.current_buffer.cancel_completion()

    @ctx.bind("escape", filter=ctx.search_widget_focus, note_activity=True)
    def _close_search(event) -> None:
        ctx.editor.close_search()

    @ctx.bind("enter", filter=ctx.search_focus, note_activity=True, invalidate=True)
    def _search_next(event) -> None:
        ctx.editor.search_step(1)

    @ctx.bind(
        "escape",
        "[",
        "1",
        "3",
        ";",
        "2",
        "u",
        filter=ctx.search_focus,
        note_activity=True,
        invalidate=True,
    )
    def _search_previous_shift(event) -> None:
        ctx.editor.search_step(-1)

    @ctx.bind("up", filter=ctx.search_focus, note_activity=True, invalidate=True)
    def _search_history_previous(event) -> None:
        ctx.editor.cycle_search_history(-1)

    @ctx.bind("down", filter=ctx.search_focus, note_activity=True, invalidate=True)
    def _search_history_next(event) -> None:
        ctx.editor.cycle_search_history(1)

    @ctx.bind("f6", filter=ctx.search_widget_focus, note_activity=True, invalidate=True)
    def _toggle_match_case(event) -> None:
        ctx.editor.toggle_match_case()

    @ctx.bind("f7", filter=ctx.search_widget_focus, note_activity=True, invalidate=True)
    def _toggle_match_whole_word(event) -> None:
        ctx.editor.toggle_match_whole_word()

    @ctx.bind("f8", filter=ctx.search_widget_focus, note_activity=True, invalidate=True)
    def _toggle_regex(event) -> None:
        ctx.editor.toggle_regex()

    @ctx.bind(
        "c-f6",
        filter=ctx.search_widget_focus & ctx.is_replace_visible,
        note_activity=True,
        invalidate=True,
    )
    def _toggle_preserve_case(event) -> None:
        ctx.editor.toggle_preserve_case()

    @ctx.bind("enter", filter=ctx.replace_focus, note_activity=True, invalidate=True)
    def _replace_current(event) -> None:
        ctx.editor.replace_current()

    @ctx.bind(
        "escape",
        "[",
        "1",
        "3",
        ";",
        "7",
        "u",
        filter=ctx.replace_focus,
        note_activity=True,
        invalidate=True,
    )
    def _replace_all(event) -> None:
        """Handle Ctrl+Alt+Enter terminals that report modifyOtherKeys"""
        ctx.editor.replace_all()

    @ctx.bind("escape", filter=ctx.jump_focus, note_activity=True)
    def _close_jump(event) -> None:
        ctx.editor.close_jump()

    @ctx.bind("enter", filter=ctx.jump_focus, note_activity=True, invalidate=True)
    def _submit_jump(event) -> None:
        ctx.editor.submit_jump()

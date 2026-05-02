"""Runtime-focused regression entrypoints for the modular editor package."""

import pytest

import _editor_interactive_cases as cases

pytestmark = pytest.mark.asyncio

test_interactive_bindings_register_supported_runtime_keys = (
    cases.test_interactive_bindings_register_supported_runtime_keys
)
test_interactive_editor_runtime_handles_bracketed_paste = (
    cases.test_interactive_editor_runtime_handles_bracketed_paste
)
test_interactive_editor_runtime_paste_preserves_undo_redo_history = (
    cases.test_interactive_editor_runtime_paste_preserves_undo_redo_history
)
test_interactive_editor_runtime_save_returns_live_buffer = (
    cases.test_interactive_editor_runtime_save_returns_live_buffer
)
test_interactive_editor_runtime_quit_confirmation_can_cancel = (
    cases.test_interactive_editor_runtime_quit_confirmation_can_cancel
)
test_interactive_editor_runtime_paste_replaces_selection = (
    cases.test_interactive_editor_runtime_paste_replaces_selection
)
test_interactive_editor_runtime_handles_modified_insert_sequences = (
    cases.test_interactive_editor_runtime_handles_modified_insert_sequences
)
test_interactive_editor_runtime_search_opens_and_closes_cleanly = (
    cases.test_interactive_editor_runtime_search_opens_and_closes_cleanly
)
test_interactive_editor_runtime_help_returns_focus_to_search = (
    cases.test_interactive_editor_runtime_help_returns_focus_to_search
)
test_interactive_editor_runtime_search_selection_clears_on_navigation = (
    cases.test_interactive_editor_runtime_search_selection_clears_on_navigation
)
test_interactive_editor_runtime_search_widget_shortcuts_work = (
    cases.test_interactive_editor_runtime_search_widget_shortcuts_work
)
test_interactive_editor_runtime_replace_enter_and_ctrl_alt_enter = (
    cases.test_interactive_editor_runtime_replace_enter_and_ctrl_alt_enter
)
test_interactive_editor_erases_screen_when_done = (
    cases.test_interactive_editor_erases_screen_when_done
)
test_interactive_editor_toolbar_and_token_status_follow_mode = (
    cases.test_interactive_editor_toolbar_and_token_status_follow_mode
)
test_interactive_editor_word_wrap_follows_setting = (
    cases.test_interactive_editor_word_wrap_follows_setting
)
test_interactive_editor_toggle_word_wrap_updates_window_and_status = (
    cases.test_interactive_editor_toggle_word_wrap_updates_window_and_status
)

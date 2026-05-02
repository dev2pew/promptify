"""Overlay and issue-mode regression entrypoints for the modular editor package."""

import pytest

import _editor_interactive_cases as cases

pytestmark = pytest.mark.asyncio

test_interactive_overlay_windows_use_responsive_dimensions = (
    cases.test_interactive_overlay_windows_use_responsive_dimensions
)
test_interactive_editor_help_restores_search_cursor_and_selection = (
    cases.test_interactive_editor_help_restores_search_cursor_and_selection
)
test_interactive_editor_quit_confirmation_restores_help_focus = (
    cases.test_interactive_editor_quit_confirmation_restores_help_focus
)
test_interactive_editor_help_suspends_quit_modal_cleanly = (
    cases.test_interactive_editor_help_suspends_quit_modal_cleanly
)
test_interactive_editor_help_suspends_error_modal_cleanly = (
    cases.test_interactive_editor_help_suspends_error_modal_cleanly
)
test_interactive_editor_collects_save_issues_for_missing_symbols = (
    cases.test_interactive_editor_collects_save_issues_for_missing_symbols
)
test_interactive_editor_issue_mode_tracks_issue_navigation = (
    cases.test_interactive_editor_issue_mode_tracks_issue_navigation
)
test_interactive_editor_uses_ascii_eof_markers_for_legacy_cmd = (
    cases.test_interactive_editor_uses_ascii_eof_markers_for_legacy_cmd
)

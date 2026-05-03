"""Search, replace, and jump regression entrypoints for the modular editor package"""

import pytest

from . import _editor_interactive_cases as cases

pytestmark = pytest.mark.asyncio

test_parse_jump_target_accepts_supported_formats = (
    cases.test_parse_jump_target_accepts_supported_formats
)
test_interactive_editor_jump_moves_cursor_and_closes_on_success = (
    cases.test_interactive_editor_jump_moves_cursor_and_closes_on_success
)
test_interactive_editor_jump_rejects_invalid_targets = (
    cases.test_interactive_editor_jump_rejects_invalid_targets
)
test_interactive_editor_jump_defaults_to_current_cursor_target = (
    cases.test_interactive_editor_jump_defaults_to_current_cursor_target
)
test_interactive_editor_jump_clears_stale_text_between_sessions = (
    cases.test_interactive_editor_jump_clears_stale_text_between_sessions
)
test_interactive_editor_search_step_moves_forward_and_backward = (
    cases.test_interactive_editor_search_step_moves_forward_and_backward
)
test_interactive_editor_search_status_reports_active_match_counts = (
    cases.test_interactive_editor_search_status_reports_active_match_counts
)
test_interactive_editor_search_toggle_fragments_use_on_off_styles = (
    cases.test_interactive_editor_search_toggle_fragments_use_on_off_styles
)
test_interactive_editor_search_reuses_session_history = (
    cases.test_interactive_editor_search_reuses_session_history
)
test_interactive_editor_search_history_moves_with_up_and_down = (
    cases.test_interactive_editor_search_history_moves_with_up_and_down
)
test_interactive_editor_search_toggles_affect_matching = (
    cases.test_interactive_editor_search_toggles_affect_matching
)
test_interactive_editor_replace_current_and_all = (
    cases.test_interactive_editor_replace_current_and_all
)
test_interactive_editor_replace_preserve_case = (
    cases.test_interactive_editor_replace_preserve_case
)
test_interactive_editor_replace_uses_regex_groups = (
    cases.test_interactive_editor_replace_uses_regex_groups
)

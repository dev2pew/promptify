"""Lexer, completion, and layout regression entrypoints for the modular editor package."""

import pytest

import _editor_interactive_cases as cases

pytestmark = pytest.mark.asyncio

test_interactive_editor_completer_surfaces_full_ranked_path_results = (
    cases.test_interactive_editor_completer_surfaces_full_ranked_path_results
)
test_interactive_completion_menu_respects_available_width = (
    cases.test_interactive_completion_menu_respects_available_width
)
test_interactive_editor_lexer_flags_incomplete_project_mentions = (
    cases.test_interactive_editor_lexer_flags_incomplete_project_mentions
)
test_interactive_editor_lexer_flags_unclosed_code_fences = (
    cases.test_interactive_editor_lexer_flags_unclosed_code_fences
)
test_interactive_editor_lexer_distinguishes_unresolved_references = (
    cases.test_interactive_editor_lexer_distinguishes_unresolved_references
)
test_interactive_editor_line_number_gutter_follows_setting = (
    cases.test_interactive_editor_line_number_gutter_follows_setting
)

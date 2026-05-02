"""Stable editor package export smoke tests."""

from promptify.ui import editor as editor_module
from promptify.ui.editor import (
    CustomPromptLexer,
    HelpLexer,
    InteractiveEditor,
    MentionCompleter,
    ResponsiveCompletionsMenu,
    VerticalSeparatorMargin,
    build_jump_target,
    parse_jump_target,
)


def test_editor_package_preserves_stable_public_exports():
    """The package-backed editor surface should keep promptify-owned imports stable."""
    assert editor_module.InteractiveEditor is InteractiveEditor
    assert editor_module.CustomPromptLexer is CustomPromptLexer
    assert editor_module.HelpLexer is HelpLexer
    assert editor_module.MentionCompleter is MentionCompleter
    assert editor_module.ResponsiveCompletionsMenu is ResponsiveCompletionsMenu
    assert editor_module.VerticalSeparatorMargin is VerticalSeparatorMargin
    assert editor_module.parse_jump_target is parse_jump_target
    assert editor_module.build_jump_target is build_jump_target

"""Stable public editor import surface backed by modular editor submodules."""

from ...shared.editor_support import build_jump_target, parse_jump_target
from ._imports import Application, get_app
from .completion import MentionCompleter, ResponsiveCompletionsMenu
from .lexers import CustomPromptLexer, HelpLexer
from .processors import VerticalSeparatorMargin
from .runtime import InteractiveEditor

__all__ = [
    "InteractiveEditor",
    "CustomPromptLexer",
    "HelpLexer",
    "MentionCompleter",
    "ResponsiveCompletionsMenu",
    "VerticalSeparatorMargin",
    "parse_jump_target",
    "build_jump_target",
    "Application",
    "get_app",
]

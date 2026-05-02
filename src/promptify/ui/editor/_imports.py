"""Shared import boundary for prompt-toolkit and optional editor dependencies."""

from __future__ import annotations

import sys

from ..logger import log
from ...utils.i18n import get_string

try:
    from prompt_toolkit import Application
    from prompt_toolkit.application.current import get_app
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.completion import CompleteEvent, Completer, Completion
    from prompt_toolkit.data_structures import Point
    from prompt_toolkit.document import Document
    from prompt_toolkit.filters import (
        Condition,
        FilterOrBool,
        has_completions,
        is_done,
        to_filter,
    )
    from prompt_toolkit.formatted_text import (
        AnyFormattedText,
        StyleAndTextTuples,
        fragment_list_width,
        to_formatted_text,
    )
    from prompt_toolkit.formatted_text.base import OneStyleAndTextTuple
    from prompt_toolkit.key_binding import merge_key_bindings
    from prompt_toolkit.key_binding.defaults import load_key_bindings
    from prompt_toolkit.layout.containers import (
        ConditionalContainer,
        Float,
        FloatContainer,
        HSplit,
        ScrollOffsets,
        VSplit,
        Window,
        WindowAlign,
    )
    from prompt_toolkit.layout.controls import (
        BufferControl,
        FormattedTextControl,
        UIContent,
    )
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.layout.margins import Margin, NumberedMargin, ScrollbarMargin
    from prompt_toolkit.layout.menus import CompletionsMenuControl
    from prompt_toolkit.layout.processors import (
        AppendAutoSuggestion,
        BeforeInput,
        HighlightMatchingBracketProcessor,
        Processor,
        Transformation,
    )
    from prompt_toolkit.layout.utils import explode_text_fragments
    from prompt_toolkit.lexers import Lexer
    from prompt_toolkit.selection import SelectionState
    from prompt_toolkit.styles import Style
    from prompt_toolkit.utils import get_cwidth
except ImportError:
    log.err(
        get_string(
            "err_prompt_toolkit_missing",
            "'prompt_toolkit' library is missing. install it using: 'uv pip install prompt_toolkit'",
        )
    )
    sys.exit(1)

try:
    import pygments  # NOQA: F401
    from pygments.lexers.markup import MarkdownLexer
    from prompt_toolkit.lexers import PygmentsLexer

    HAS_PYGMENTS = True
except ImportError:
    MarkdownLexer = None
    PygmentsLexer = None
    HAS_PYGMENTS = False
    log.warn(
        get_string(
            "err_pygments_missing",
            "'pygments' library is missing. syntax highlighting will be disabled. install it using: 'uv pip install pygments'",
        )
    )

try:
    from rapidfuzz import process as _rapidfuzz_process  # NOQA: F401
except ImportError:
    log.err(
        get_string(
            "err_rapidfuzz_missing",
            "'rapidfuzz' library is missing. install it using: 'uv pip install rapidfuzz'",
        )
    )
    sys.exit(1)

__all__ = [
    "Application",
    "get_app",
    "Buffer",
    "CompleteEvent",
    "Completer",
    "Completion",
    "Point",
    "Document",
    "Condition",
    "FilterOrBool",
    "has_completions",
    "is_done",
    "to_filter",
    "AnyFormattedText",
    "StyleAndTextTuples",
    "fragment_list_width",
    "to_formatted_text",
    "OneStyleAndTextTuple",
    "merge_key_bindings",
    "load_key_bindings",
    "ConditionalContainer",
    "Float",
    "FloatContainer",
    "HSplit",
    "ScrollOffsets",
    "VSplit",
    "Window",
    "WindowAlign",
    "BufferControl",
    "FormattedTextControl",
    "UIContent",
    "Dimension",
    "Layout",
    "Margin",
    "NumberedMargin",
    "ScrollbarMargin",
    "CompletionsMenuControl",
    "AppendAutoSuggestion",
    "BeforeInput",
    "HighlightMatchingBracketProcessor",
    "Processor",
    "Transformation",
    "explode_text_fragments",
    "Lexer",
    "SelectionState",
    "Style",
    "get_cwidth",
    "MarkdownLexer",
    "PygmentsLexer",
    "HAS_PYGMENTS",
]

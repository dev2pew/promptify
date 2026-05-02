"""Prompt-toolkit processors and margins used by the interactive editor."""

from __future__ import annotations

from typing import Callable, cast

from ...core.terminal import TerminalProfile
from ...shared.editor_state import SearchHighlightState
from ...shared.editor_support import (
    append_original_token_range,
    flatten_fragments_to_chars,
    fragment_text,
)
from ._imports import (
    Margin,
    Processor,
    StyleAndTextTuples,
    Transformation,
    UIContent,
    get_app,
)


class HighlightTrailingWhitespaceProcessor(Processor):
    """Highlight trailing spaces and tabs at the end of each line."""

    def apply_transformation(self, transformation_input):
        fragments = transformation_input.fragments
        if not fragments:
            return Transformation(fragments)

        line_text = "".join(fragment_text(fragment) for fragment in fragments)
        stripped = line_text.rstrip(" \t")
        if len(stripped) == len(line_text):
            return Transformation(fragments)

        new_fragments = []
        char_count = 0
        for fragment in fragments:
            style = cast(str, fragment[0])
            text = fragment_text(fragment)
            if char_count >= len(stripped):
                new_fragments.append(("class:trailing-whitespace", text))
            elif char_count + len(text) > len(stripped):
                split_idx = len(stripped) - char_count
                new_fragments.append((style, text[:split_idx]))
                new_fragments.append(("class:trailing-whitespace", text[split_idx:]))
            else:
                new_fragments.append((style, text))
            char_count += len(text)

        return Transformation(new_fragments)


class EOFNewlineProcessor(Processor):
    """Visually indicate a missing EOF newline."""

    def __init__(self, terminal_profile: TerminalProfile):
        self.terminal_profile = terminal_profile

    def apply_transformation(self, transformation_input):
        document = transformation_input.document
        lineno = transformation_input.lineno
        tokens = transformation_input.fragments
        if lineno == document.line_count - 1:
            if document.text.endswith("\n") or not document.text:
                tokens = tokens + [
                    ("class:eof-newline", self.terminal_profile.eof_newline_present)
                ]
            else:
                tokens = tokens + [
                    ("class:eof-newline", self.terminal_profile.eof_newline_missing)
                ]
        return Transformation(tokens)


class SearchMatchProcessor(Processor):
    """Highlight search matches with distinct active and passive styles."""

    def __init__(self, get_state: Callable[[], SearchHighlightState | None]):
        self.get_state = get_state

    def apply_transformation(self, transformation_input):
        state = self.get_state()
        if state is None or not state.query or not state.matches:
            return Transformation(transformation_input.fragments)

        line_text = "".join(
            fragment_text(fragment) for fragment in transformation_input.fragments
        )
        if not line_text:
            return Transformation(transformation_input.fragments)

        line_start = transformation_input.document.translate_row_col_to_index(
            transformation_input.lineno, 0
        )
        line_end = line_start + len(line_text)
        ranges: list[tuple[int, int, str]] = []
        for match in state.matches:
            if match.end <= line_start:
                continue
            if match.start >= line_end:
                break
            start = max(0, match.start - line_start)
            end = min(len(line_text), match.end - line_start)
            style = (
                "class:search-match-active"
                if state.active_match == match
                else "class:search-match"
            )
            ranges.append((start, end, style))

        if not ranges:
            return Transformation(transformation_input.fragments)

        new_fragments = []
        char_index = 0
        for fragment in transformation_input.fragments:
            base_style = cast(str, fragment[0])
            text = fragment_text(fragment)
            if not text:
                new_fragments.append(fragment)
                continue

            segment_start = char_index
            segment_end = char_index + len(text)
            cursor = segment_start
            for range_start, range_end, highlight_style in ranges:
                if range_end <= segment_start or range_start >= segment_end:
                    continue

                overlap_start = max(segment_start, range_start)
                overlap_end = min(segment_end, range_end)
                if overlap_start > cursor:
                    new_fragments.append(
                        (
                            base_style,
                            text[
                                cursor - segment_start : overlap_start - segment_start
                            ],
                        )
                    )
                new_fragments.append(
                    (
                        f"{base_style} {highlight_style}".strip(),
                        text[
                            overlap_start - segment_start : overlap_end - segment_start
                        ],
                    )
                )
                cursor = overlap_end

            if cursor < segment_end:
                new_fragments.append((base_style, text[cursor - segment_start :]))
            char_index = segment_end

        return Transformation(new_fragments)


class ActiveLineProcessor(Processor):
    """Soft-highlight the current logical line in the main editor buffer."""

    def apply_transformation(self, transformation_input):
        try:
            app = get_app()
        except Exception:
            return Transformation(transformation_input.fragments)
        if (
            transformation_input.lineno
            != app.current_buffer.document.cursor_position_row
        ):
            return Transformation(transformation_input.fragments)

        tokens: list[tuple[object, ...]] = []
        chars = flatten_fragments_to_chars(transformation_input.fragments)
        if not chars:
            return Transformation(transformation_input.fragments)
        append_original_token_range(tokens, chars, 0, len(chars))
        return Transformation(
            [
                (
                    f"{str(fragment[0]) or ''} class:current-line".strip(),
                    fragment_text(fragment),
                )
                for fragment in tokens
            ]
        )


class VerticalSeparatorMargin(Margin):
    """Render a single-column separator next to the optional line-number gutter."""

    def __init__(self, terminal_profile: TerminalProfile):
        self._separator = terminal_profile.tree.vertical

    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        return 1

    def create_margin(
        self, window_render_info, width: int, height: int
    ) -> StyleAndTextTuples:
        del window_render_info, width
        return [("class:editor-frame.border", (self._separator + "\n") * height)]

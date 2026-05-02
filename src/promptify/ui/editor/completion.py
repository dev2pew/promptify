"""Autocomplete components used by the interactive editor."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Callable, cast

from ...core.indexer import ProjectIndexer
from ...core.mods import ModRegistry
from ._imports import (
    CompleteEvent,
    Completer,
    Completion,
    CompletionsMenuControl,
    ConditionalContainer,
    Dimension,
    Document,
    FilterOrBool,
    Point,
    ScrollOffsets,
    ScrollbarMargin,
    StyleAndTextTuples,
    UIContent,
    Window,
    explode_text_fragments,
    fragment_list_width,
    get_app,
    get_cwidth,
    has_completions,
    is_done,
    to_filter,
    to_formatted_text,
)


class MentionCompleter(Completer):
    """Route autocomplete requests through the registered mods."""

    def __init__(
        self,
        indexer: ProjectIndexer,
        registry: ModRegistry,
        should_complete: Callable[[Document], bool],
    ):
        self.indexer = indexer
        self.registry = registry
        self.should_complete = should_complete

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        if not self.should_complete(document):
            return
        completions = list(
            self.registry.get_all_completions(document.text_before_cursor, self.indexer)
        )
        yield from completions


class ResponsiveCompletionsMenuControl(CompletionsMenuControl):
    """Completion menu control that respects the active viewport width."""

    MIN_LABEL_COLUMN_WIDTH = 16
    MIN_META_COLUMN_WIDTH = 12
    MIN_WIDTH_FOR_META = 28
    MAX_VIEWPORT_WIDTH_RATIO = 0.72
    MAX_LABEL_WIDTH_RATIO = 0.58
    MAX_META_WIDTH_RATIO = 0.5

    def _get_display_text_width(self, text: str) -> int:
        """Measure display text consistently with prompt-toolkit cell widths."""
        return get_cwidth(text)

    def _trim_formatted_text_left(
        self, formatted_text: StyleAndTextTuples, max_width: int
    ) -> tuple[StyleAndTextTuples, int]:
        """Trim from the left so long paths keep their most relevant tail."""
        width = fragment_list_width(formatted_text)
        if width <= max_width:
            return formatted_text, width
        if max_width <= 3:
            dots = "." * max(0, max_width)
            return [("", dots)], len(dots)

        remaining_width = max_width - 3
        tail = []
        for style_and_ch in reversed(list(explode_text_fragments(formatted_text))):
            ch_width = get_cwidth(style_and_ch[1])
            if ch_width <= remaining_width:
                tail.append(style_and_ch)
                remaining_width -= ch_width
            else:
                break

        tail.reverse()
        result: StyleAndTextTuples = [("", "...")]
        result.extend(tail)
        return result, max_width - remaining_width

    def _get_label_fragments(
        self, completion: Completion, is_current_completion: bool, width: int
    ) -> StyleAndTextTuples:
        """Render the label column with suffix-first trimming on overflow."""
        if is_current_completion:
            style_str = (
                "class:completion-menu.completion.current "
                f"{completion.style} {completion.selected_style}"
            )
        else:
            style_str = "class:completion-menu.completion " + completion.style
        return self._get_trimmed_column_fragments(
            to_formatted_text(completion.display),
            style_str,
            width,
            trim_delta=1,
        )

    def _get_trimmed_column_fragments(
        self,
        content: StyleAndTextTuples,
        style_str: str,
        width: int,
        trim_delta: int,
        padding_delta: int = 1,
    ) -> StyleAndTextTuples:
        """Trim and pad a single completion column consistently."""
        text, text_width = self._trim_formatted_text_left(content, width - trim_delta)
        padding = " " * max(0, width - padding_delta - text_width)
        return to_formatted_text(
            cast(StyleAndTextTuples, []) + [("", " ")] + text + [("", padding)],
            style=style_str,
        )

    def _get_width_budget(self, max_available_width: int) -> int:
        """Keep the popup responsive by capping it below the full viewport."""
        if max_available_width <= self.MIN_WIDTH_FOR_META:
            return max_available_width
        capped_width = int(max_available_width * self.MAX_VIEWPORT_WIDTH_RATIO)
        return max(self.MIN_WIDTH_FOR_META, min(max_available_width, capped_width))

    def preferred_width(self, max_available_width: int) -> int | None:
        complete_state = get_app().current_buffer.complete_state
        if not complete_state:
            return 0

        width_budget = self._get_width_budget(max_available_width)
        menu_width = self._get_menu_width(width_budget, complete_state)
        menu_meta_width = self._get_menu_meta_width(
            max(0, width_budget - menu_width), complete_state
        )
        preferred = menu_width + menu_meta_width
        return min(width_budget, preferred)

    def _get_column_widths(self, width: int, complete_state) -> tuple[int, int, bool]:
        """Split available width between the label and path metadata columns."""
        show_meta = self._show_meta(complete_state)
        natural_label_width = self._get_menu_width(width, complete_state)
        natural_meta_width = self._get_menu_meta_width(width, complete_state)
        if not show_meta or width < self.MIN_WIDTH_FOR_META:
            return min(width, natural_label_width), 0, False

        label_content_width = max(self.MIN_WIDTH, natural_label_width)
        meta_content_width = max(self.MIN_META_COLUMN_WIDTH, natural_meta_width)
        natural_total = label_content_width + meta_content_width
        label_ratio = label_content_width / natural_total if natural_total else 0.5
        label_ratio = max(0.4, min(self.MAX_LABEL_WIDTH_RATIO, label_ratio))

        label_width = max(
            self.MIN_LABEL_COLUMN_WIDTH,
            min(int(width * label_ratio), int(width * self.MAX_LABEL_WIDTH_RATIO)),
        )
        label_width = min(label_width, width - self.MIN_META_COLUMN_WIDTH)
        meta_width = width - label_width

        max_meta_width = max(
            self.MIN_META_COLUMN_WIDTH, int(width * self.MAX_META_WIDTH_RATIO)
        )
        if meta_width > max_meta_width:
            shift = meta_width - max_meta_width
            meta_width -= shift
            label_width = min(width - meta_width, label_width + shift)

        label_width = min(label_width, natural_label_width)
        meta_width = width - label_width
        if (
            label_width < self.MIN_LABEL_COLUMN_WIDTH
            or meta_width < self.MIN_META_COLUMN_WIDTH
        ):
            return min(width, natural_label_width), 0, False
        if natural_meta_width < self.MIN_META_COLUMN_WIDTH:
            return min(width, natural_label_width), 0, False

        meta_width = min(
            meta_width,
            max(self.MIN_META_COLUMN_WIDTH, natural_meta_width),
        )
        label_width = width - meta_width
        if label_width < self.MIN_LABEL_COLUMN_WIDTH:
            return min(width, natural_label_width), 0, False
        return label_width, meta_width, True

    def _get_menu_item_meta_fragments(
        self, completion: Completion, is_current_completion: bool, width: int
    ) -> StyleAndTextTuples:
        """Render path metadata from the right so the tail stays visible."""
        style_str = (
            "class:completion-menu.meta.completion.current"
            if is_current_completion
            else "class:completion-menu.meta.completion"
        )
        return self._get_trimmed_column_fragments(
            to_formatted_text(completion.display_meta),
            style_str,
            width,
            trim_delta=2,
        )

    def create_content(self, width: int, height: int) -> UIContent:
        """Render completions using a viewport-aware label and metadata split."""
        complete_state = get_app().current_buffer.complete_state
        if not complete_state:
            return UIContent()

        completions = complete_state.completions
        index = complete_state.complete_index
        menu_width, meta_width, show_meta = self._get_column_widths(
            width, complete_state
        )

        def get_line(i: int):
            completion = completions[i]
            is_current_completion = i == index
            result = self._get_label_fragments(
                completion, is_current_completion, menu_width
            )
            if show_meta:
                result += self._get_menu_item_meta_fragments(
                    completion, is_current_completion, meta_width
                )
            return result

        return UIContent(
            get_line=get_line,
            cursor_position=Point(x=0, y=index or 0),
            line_count=len(completions),
        )


class ResponsiveCompletionsMenu(ConditionalContainer):
    """Dropdown menu that tracks terminal size instead of a fixed width hint."""

    def __init__(
        self,
        max_height: int | None = None,
        scroll_offset: int | Callable[[], int] = 0,
        extra_filter: FilterOrBool = True,
        display_arrows: FilterOrBool = False,
        z_index: int = 10**8,
    ) -> None:
        extra_filter_filter = to_filter(extra_filter)
        display_arrows_filter = to_filter(display_arrows)
        super().__init__(
            content=Window(
                content=ResponsiveCompletionsMenuControl(),
                width=Dimension(min=8),
                height=Dimension(min=1, max=max_height),
                scroll_offsets=ScrollOffsets(top=scroll_offset, bottom=scroll_offset),
                right_margins=[ScrollbarMargin(display_arrows=display_arrows_filter)],
                dont_extend_width=True,
                style="class:completion-menu",
                z_index=z_index,
            ),
            filter=extra_filter_filter & has_completions & ~is_done,
        )

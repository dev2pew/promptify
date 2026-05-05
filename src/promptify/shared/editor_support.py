"""Shared editor-neutral helpers and constants"""

from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Sequence
from typing import cast

from ..utils.i18n import strings
from .editor_state import EditorTextEdit, MultiCursorCaret

MENTION_SCAN_PATTERN = r"<@(?:\\.|[^>\n])+(?:>|$)|\[@[^\]\n]*(?:\]|$)"
HELP_TOKEN_PATTERN = r"(<@(?:\\.|[^>\n])+>|\[@project\])|(\^?\[[^\]\n]+\])"
JUMP_TARGET_PATTERN = re.compile(r"^:(?P<line>\d+)(?:(?:[:,])(?P<column>\d+))?$")
HELP_TEXT_FALLBACK = (
    "[ general ]\n\n"
    "^[G] / [F1]                   : help\n\n"
    "^[F]                          : search\n"
    "^[R]                          : replace\n"
    "^[S]                          : resolve\n"
    "^[^/v]                        : scroll view\n\n"
    "[Alt] + [G]                   : jump to line\n"
    "[Alt] + [Z]                   : word wrap\n"
    "[Esc]                         : close pane\n\n"
    "^[Q] / [F10]                  : abort\n"
    "[ search ]\n\n"
    "[Enter]                       : next\n\n"
    "[Shift] + [Enter]             : previous\n"
    "[^/v]                         : history\n"
    "[F6] / [F7] / [F8]            : case / word / regex\n"
    "[ replace ]\n\n"
    "[Enter]                       : replace\n\n"
    "^[Alt] + [Enter]              : replace all\n"
    "^[F6]                         : preserve case\n"
    "[ jump ]\n\n"
    "[Enter]                       : jump\n\n"
    "[ issues ]\n\n"
    "[Enter] / ^[N]                : next\n\n"
    "^[R] / ^[P]                   : previous\n"
    "[ autocomplete mentions ]\n\n"
    "<@file:path>                  : file\n\n"
    "<@symbol:path:name>           : symbol\n"
    "<@file:path:range>            : slice file\n\n"
    "            first n           : head\n"
    "            last n            : tail\n"
    "            n-m               : ranged\n"
    "            #n                : single\n"
    "<@dir:path>                   : directory\n\n"
    "<@tree:path>                  : tree\n\n"
    "<@tree:path:level>            : set depth\n"
    "<@ext:list>                   : type\n\n"
    "<@git:diff>                   : work tree diff\n\n"
    "<@git:diff:path>              : work tree file diff\n"
    "<@git:status>                 : work tree status\n\n"
    "<@git:log>                    : recent log (20)\n\n"
    "<@git:log:count>              : set length\n"
    "<@git:history>                : recent log w/diff (5)\n\n"
    "<@git:history:count>          : set length\n"
    "<@git:[branch]:subcommand>    : set branch-scope\n\n"
    "<@git:[branch]:diff:path>     : ex.\n"
    "<@git:[branch]:log:count>     : ex.\n"
    "<@git:[branch]:history:count> : ex.\n"
    "[@project]                    : project structure\n\n"
    "[ editing ]\n\n"
    "[Shift]                       : select\n\n"
    "^[A]                          : select all\n"
    "^[D]                          : select next occurrence\n"
    "^[Shift] + [L]                : select all occurrences\n"
    "^[Z/Y]                        : undo / redo\n\n"
    "^[C/X/V]                      : copy / cut / paste\n"
    "^[Shift] + [C/V]              : copy / paste alias\n"
    "[Tab]                         : indent / autocomplete\n\n"
    "[Shift] + [Tab]               : unindent\n"
    "[Shift] + [Alt] + [^/v]       : clone below / above\n\n"
    "[Alt] + [^/v]                 : shift up / down\n"
    "[specials]                    : wrap selection\n"
    "^[/]                          : comment out\n\n"
    "^[W/Del]                      : delete previous / next\n"
    "^[Alt] + [^/v]                : cursor above / below\n\n"
    "^[Shift] + [Alt] + [^/v]      : cursor expand / shrink\n"
    "[ navigation ]\n\n"
    "[^/v/</>]                     : move\n\n"
    "^[^/v/</>]                    : next / previous\n"
    "[Home/End]                    : start / end\n"
    "^[Home/End]                   : file start / end\n"
    "^[PgUp/PgDn]                  : up / down (15)\n"
    "press [Enter], [F1] or ^[G] to close"
)


@dataclass(frozen=True, slots=True)
class LogicalLineSpan:
    """Describe one logical line plus its edit-friendly boundary metadata"""

    start: int
    end: int
    row: int
    line_count: int
    text: str
    previous_row_start: int

    def cut_range(self) -> tuple[int, int]:
        """Return the VS Code-like deletion span for removing this line"""
        if self.row < self.line_count - 1:
            return self.start, self.end + 1
        if self.row > 0:
            return self.start - 1, self.end
        return self.start, self.end

    def cut_target_position(self) -> int:
        """Return the cursor location left behind after cutting this line"""
        return self.previous_row_start if self.row > 0 else self.start

    def clone_insertion(self, *, insert_above: bool) -> tuple[int, str]:
        """Return the insertion point and payload for cloning this line"""
        if insert_above:
            return self.start, self.text + "\n"
        if self.row < self.line_count - 1:
            return self.end + 1, self.text + "\n"
        return self.end, "\n" + self.text


@dataclass(frozen=True, slots=True)
class EditorBufferContext:
    """Capture the active markdown or fenced-code context at one cursor position"""

    in_fenced_block: bool
    language_key: str
    wrap_lookup_keys: tuple[str, ...]


def fragment_text(fragment: tuple[object, ...]) -> str:
    """Read prompt-toolkit fragments that may carry an optional third field"""
    if len(fragment) < 2 or not isinstance(fragment[1], str):
        return ""
    return fragment[1]


def flatten_fragments_to_chars(
    fragments: Sequence[tuple[object, ...]],
) -> list[tuple[str, str]]:
    """Flatten fragments into style and character pairs for safe rewrites"""
    chars: list[tuple[str, str]] = []
    for fragment in fragments:
        style = cast(str, fragment[0])
        for char in fragment_text(fragment):
            chars.append((style, char))
    return chars


def append_original_token_range(
    tokens: list[tuple[object, ...]],
    chars: list[tuple[str, str]],
    start: int,
    end: int,
) -> None:
    """Restore a style-preserving token slice from flattened character data"""
    curr_style = ""
    curr_text: list[str] = []
    for index in range(start, end):
        style, char = chars[index]
        if style != curr_style:
            if curr_text:
                tokens.append((curr_style, "".join(curr_text)))
            curr_style = style
            curr_text = [char]
        else:
            curr_text.append(char)

    if curr_text:
        tokens.append((curr_style, "".join(curr_text)))


def parse_jump_target(text: str) -> tuple[int, int] | None:
    """Parse a 1-based line and optional character target from the jump bar"""
    match = JUMP_TARGET_PATTERN.fullmatch(text.strip())
    if match is None:
        return None
    line = int(match.group("line"))
    column_text = match.group("column")
    column = 1 if column_text is None else int(column_text)
    return line, column


def build_jump_target(line: int, column: int) -> str:
    """Format a 1-based cursor location for jump-mode display and parsing"""
    return f":{line}:{column}"


def preserve_replacement_case(source: str, replacement: str) -> str:
    """Mirror simple source casing patterns onto a replacement string"""
    if not source or not replacement:
        return replacement
    if source.isupper():
        return replacement.upper()
    if source.islower():
        return replacement.lower()
    if source.istitle():
        return replacement.title()
    if len(source) == 1 and source.isalpha():
        return replacement.upper() if source.isupper() else replacement.lower()
    if source[0].isupper() and source[1:].islower():
        head = replacement[:1].upper()
        tail = replacement[1:].lower()
        return head + tail
    return replacement


def get_logical_line_span(text: str, position: int) -> LogicalLineSpan:
    """Resolve one logical line around a character position"""
    clamped = max(0, min(len(text), position))
    start = text.rfind("\n", 0, clamped) + 1
    end = text.find("\n", clamped)
    if end < 0:
        end = len(text)
    row = text.count("\n", 0, start)
    line_count = text.count("\n") + 1
    previous_row_start = start
    if row > 0:
        previous_row_start = text.rfind("\n", 0, start - 1) + 1
    return LogicalLineSpan(
        start=start,
        end=end,
        row=row,
        line_count=line_count,
        text=text[start:end],
        previous_row_start=previous_row_start,
    )


def get_active_editor_context(text: str, position: int) -> EditorBufferContext:
    """Resolve whether the caret lives in markdown or a fenced code block"""
    line_start = text.rfind("\n", 0, max(0, min(len(text), position))) + 1
    lines_before = text[:line_start].splitlines()
    in_block = False
    language = ""
    for line in lines_before:
        stripped = line.strip()
        if not stripped.startswith("```"):
            continue
        if in_block:
            in_block = False
            language = ""
        else:
            in_block = True
            language = stripped[3:].strip().lower()

    keys: list[str] = []
    if in_block and language:
        keys.append(language)
    keys.append("markdown")
    keys.append("default")
    return EditorBufferContext(
        in_fenced_block=in_block,
        language_key=language,
        wrap_lookup_keys=tuple(dict.fromkeys(keys)),
    )


def get_editor_wrap_pair(
    text: str,
    position: int,
    trigger: str,
) -> tuple[str, str] | None:
    """Look up a wrap pair for one trigger in the active editor context"""
    if not trigger:
        return None
    wrap_registry = strings.get("editor_wrap_symbols")
    if not isinstance(wrap_registry, dict):
        return None
    context = get_active_editor_context(text, position)
    for key in context.wrap_lookup_keys:
        context_pairs = wrap_registry.get(key)
        if not isinstance(context_pairs, dict):
            continue
        pair = context_pairs.get(trigger)
        if (
            isinstance(pair, list)
            and len(pair) >= 2
            and isinstance(pair[0], str)
            and isinstance(pair[1], str)
        ):
            return cast(str, pair[0]), cast(str, pair[1])
    return None


def apply_editor_text_edits(
    text: str,
    edits: Sequence[EditorTextEdit],
) -> tuple[str, list[MultiCursorCaret]]:
    """Apply ordered text edits and resolve their resulting caret positions"""
    if not edits:
        return text, []

    ordered = sorted(edits, key=lambda item: (item.start, item.end))
    parts: list[str] = []
    last_index = 0
    for edit in ordered:
        parts.append(text[last_index : edit.start])
        parts.append(edit.replacement)
        last_index = edit.end
    parts.append(text[last_index:])
    new_text = "".join(parts)

    new_carets: list[MultiCursorCaret] = []
    for edit in ordered:
        for caret in edit.carets:
            anchor = None
            if caret.anchor_source_position is not None:
                anchor = _rebase_edit_target_position(
                    source_position=caret.anchor_source_position,
                    replacement_offset=caret.anchor_replacement_offset,
                    target_edit=edit,
                    ordered_edits=ordered,
                )
            new_carets.append(
                MultiCursorCaret(
                    position=_rebase_edit_target_position(
                        source_position=caret.source_position,
                        replacement_offset=caret.replacement_offset,
                        target_edit=edit,
                        ordered_edits=ordered,
                    ),
                    anchor=anchor,
                    preferred_column=caret.preferred_column,
                    is_primary=caret.is_primary,
                )
            )
    return new_text, new_carets


def _rebase_edit_target_position(
    *,
    source_position: int,
    replacement_offset: int,
    target_edit: EditorTextEdit,
    ordered_edits: Sequence[EditorTextEdit],
) -> int:
    """Translate one source caret or anchor target through the full edit list"""
    delta = 0
    for edit in ordered_edits:
        transformed_start = edit.start + delta
        if source_position < edit.start:
            break
        if source_position <= edit.end:
            if edit is target_edit:
                return transformed_start + min(
                    replacement_offset,
                    len(edit.replacement),
                )
            return transformed_start + min(
                source_position - edit.start, len(edit.replacement)
            )
        delta += len(edit.replacement) - (edit.end - edit.start)
    return source_position + delta

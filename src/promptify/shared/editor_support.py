"""Shared editor-neutral helpers and constants"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import cast

MENTION_SCAN_PATTERN = r"<@(?:\\.|[^>\n])+(?:>|$)|\[@[^\]\n]*(?:\]|$)"
HELP_TOKEN_PATTERN = r"(<@(?:\\.|[^>\n])+>|\[@project\])|(\^?\[[^\]\n]+\])"
JUMP_TARGET_PATTERN = re.compile(r"^:(?P<line>\d+)(?:(?:[:,])(?P<column>\d+))?$")
HELP_TEXT_FALLBACK = (
    "[ general ]\n\n"
    "^[G] / [F1]                   : help"
    "^[F]                          : search"
    "^[R]                          : replace"
    "^[S]                          : resolve\n\n"
    "^[^/v]                        : scroll view"
    "[Alt] + [G]                   : jump to line"
    "[Alt] + [Z]                   : word wrap\n\n"
    "[Esc]                         : close pane"
    "^[Q] / [F10]                  : abort\n\n"
    "[ search ]\n\n"
    "[Enter]                       : next"
    "[Shift] + [Enter]             : previous"
    "[^/v]                         : history"
    "[F6] / [F7] / [F8]            : case / word / regex\n\n"
    "[ replace ]\n\n"
    "[Enter]                       : replace"
    "^[Alt] + [Enter]              : replace all"
    "^[F6]                         : preserve case\n\n"
    "[ jump ]\n\n"
    "[Enter]                       : jump\n\n"
    "[ issues ]\n\n"
    "[Enter] / ^[N]                : next"
    "^[R] / ^[P]                   : previous\n\n"
    "[ autocomplete mentions ]\n\n"
    "<@file:path>                  : file"
    "<@symbol:path:name>           : symbol\n\n"
    "<@file:path:range>            : slice file"
    "            first n           : head"
    "            last n            : tail"
    "            n-m               : ranged"
    "#n                : single\n\n"
    "<@dir:path>                   : directory\n\n"
    "<@tree:path>                  : tree"
    "<@tree:path:level>            : set depth\n\n"
    "<@ext:list>                   : type\n\n"
    "<@git:diff>                   : work tree diff"
    "<@git:diff:path>              : work tree file diff\n\n"
    "<@git:status>                 : work tree status\n\n"
    "<@git:log>                    : recent log (20)"
    "<@git:log:count>              : set length\n\n"
    "<@git:history>                : recent log w/diff (5)"
    "<@git:history:count>          : set length\n\n"
    "<@git:[branch]:subcommand>    : set branch-scope"
    "<@git:[branch]:diff:path>     : ex."
    "<@git:[branch]:log:count>     : ex."
    "<@git:[branch]:history:count> : ex.\n\n"
    "[@project]                    : project structure\n\n"
    "[ editing ]\n\n"
    "[Shift]                       : select"
    "^[A]                          : select all"
    "^[D]                          : select next occurrence"
    "^[Shift] + [L]                : select all occurrences\n\n"
    "^[Z/Y]                        : undo / redo"
    "^[C/X/V]                      : copy / cut / paste\n\n"
    "[Tab]                         : indent / autocomplete"
    "[Shift] + [Tab]               : unindent\n\n"
    "[Alt] + [^/v]                 : shift up / down\n\n"
    "^[/]                          : comment out"
    "^[W/Del]                      : delete previous / next\n\n"
    "^[Alt] + [^/v]                : cursor above / below"
    "^[Shift] + [Alt] + [^/v]      : cursor expand / shrink\n\n"
    "[ navigation ]\n\n"
    "[^/v/</>]                     : move"
    "^[^/v/</>]                    : next / previous"
    "[Home/End]                    : start / end"
    "^[Home/End]                   : file start / end"
    "^[PgUp/PgDn]                  : up / down (15)\n\n"
    "press [Enter], [F1] or ^[G] to close"
)


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

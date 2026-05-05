"""Terminal key sequence variants used by editor bindings"""

from __future__ import annotations

from prompt_toolkit.keys import Keys

from .context import KeySequence

SHIFT_ENTER: tuple[KeySequence, ...] = (
    (Keys.Escape, "[", "1", "3", ";", "2", "u"),
    (Keys.Escape, Keys.Enter),
)

CTRL_ALT_ENTER: tuple[KeySequence, ...] = (
    (Keys.Escape, "[", "1", "3", ";", "7", "u"),
    (Keys.Escape, Keys.Enter),
)

CTRL_ALT_UP: tuple[KeySequence, ...] = (
    (Keys.Escape, "[", "1", ";", "7", "A"),
    (Keys.Escape, Keys.ControlDown),
)

CTRL_ALT_DOWN: tuple[KeySequence, ...] = (
    (Keys.Escape, "[", "1", ";", "7", "B"),
    (Keys.Escape, Keys.ControlUp),
)

CTRL_SHIFT_ALT_UP: tuple[KeySequence, ...] = (
    (Keys.Escape, "[", "1", ";", "8", "A"),
    (Keys.Escape, Keys.ControlShiftDown),
)

CTRL_SHIFT_ALT_DOWN: tuple[KeySequence, ...] = (
    (Keys.Escape, "[", "1", ";", "8", "B"),
    (Keys.Escape, Keys.ControlShiftUp),
)


CTRL_SHIFT_C: tuple[KeySequence, ...] = (
    (Keys.Escape, "[", "6", "7", ";", "6", "u"),
    (Keys.Escape, "[", "9", "9", ";", "6", "u"),
)

CTRL_SHIFT_V: tuple[KeySequence, ...] = (
    (Keys.Escape, "[", "8", "6", ";", "6", "u"),
    (Keys.Escape, "[", "1", "1", "8", ";", "6", "u"),
)

MODAL_BLOCKED_ESCAPE_SEQUENCES: tuple[KeySequence, ...] = (
    *CTRL_ALT_UP,
    *CTRL_ALT_DOWN,
    *CTRL_SHIFT_ALT_UP,
    *CTRL_SHIFT_ALT_DOWN,
    (Keys.Escape, "g"),
    (Keys.Escape, "z"),
    (Keys.Escape, Keys.Up),
    (Keys.Escape, Keys.Down),
    (Keys.Escape, "[", "1", ";", "3", "A"),
    (Keys.Escape, "[", "1", ";", "3", "B"),
)

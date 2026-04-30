"""Tests for I/O and TaskGroup-related performance boundaries"""

import asyncio
import pytest
import time

from prompt_toolkit.document import Document
from prompt_toolkit.selection import SelectionState

from promptify.ui.editor import InteractiveEditor

pytestmark = pytest.mark.asyncio


async def test_concurrent_resolution(app_components):
    """Resolving many tags concurrently should remain fast"""
    _, resolver = app_components

    # CREATE A PROMPT WITH 100 MENTIONS OF APP.PY
    prompt = " ".join(["<@file:app.py>"] * 100)

    start = time.perf_counter()
    res = await resolver.resolve_user(prompt)
    duration = time.perf_counter() - start

    # IT SHOULD RESOLVE VERY QUICKLY DUE TO TASKGROUP AND CACHING
    assert duration < 2.0

    # "THIS IS LINE 1'" (WITH QUOTE) APPEARS EXACTLY ONCE PER FILE.
    # WE CHECK FOR THE QUOTE TO AVOID MATCHING "THIS IS LINE 10", "11", ETC.
    assert res.count("This is line 1'") == 100


async def test_editor_completion_gate_only_triggers_inside_mentions(app_components):
    """Autocomplete should not scan the project for ordinary prose"""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)

    assert not editor.should_complete(Document("plain text before cursor"))
    assert editor.should_complete(Document("draft <@fi"))
    assert editor.should_complete(Document("draft [@pro"))


async def test_editor_bulk_edit_temporarily_disables_expensive_checks(app_components):
    """Large pastes should briefly suspend redraw-time validation"""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)

    assert editor.expensive_checks_enabled()

    editor.start_bulk_edit("x" * editor.BULK_EDIT_SIZE_THRESHOLD)
    assert not editor.expensive_checks_enabled()

    await asyncio.sleep(editor.BULK_EDIT_SUSPEND_SECONDS + 0.05)
    assert editor.expensive_checks_enabled()


async def test_paste_text_uses_bulk_edit_path_for_large_payloads(app_components):
    """All paste sources should use the same fast large-paste path"""
    context, resolver = app_components
    editor = InteractiveEditor("keep old text", context.indexer, resolver)
    editor.buffer.selection_state = SelectionState(original_cursor_position=0)
    editor.buffer.cursor_position = len(editor.buffer.text)

    payload = "x" * editor.BULK_EDIT_SIZE_THRESHOLD
    editor.paste_text(editor.buffer, payload)

    assert editor.buffer.text == payload
    assert editor.buffer.selection_state is None
    assert not editor.expensive_checks_enabled()

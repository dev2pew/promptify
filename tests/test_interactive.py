"""
UNIT TESTS EXERCISING THE RUNTIME INTERACTIVE EDITOR SURFACE.
"""

import asyncio

import pytest
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.keys import Keys
from prompt_toolkit.output.base import DummyOutput
from prompt_toolkit.selection import SelectionState

from promptify.ui.bindings import setup_keybindings
from promptify.ui.editor import InteractiveEditor

pytestmark = pytest.mark.asyncio


async def test_interactive_bindings_register_supported_runtime_keys(app_components):
    """KEYBINDINGS SHOULD BUILD CLEANLY AND EXPOSE THE RUNTIME PASTE ENTRYPOINTS."""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)

    bindings = setup_keybindings(editor)

    assert bindings.get_bindings_for_keys((Keys.ControlV,))
    assert bindings.get_bindings_for_keys((Keys.ShiftInsert,))
    assert bindings.get_bindings_for_keys((Keys.ControlShiftInsert,))
    assert bindings.get_bindings_for_keys((Keys.BracketedPaste,))
    assert bindings.get_bindings_for_keys((Keys.Escape, "[", "2", ";", "2", "~"))
    assert bindings.get_bindings_for_keys((Keys.Escape, "[", "2", ";", "6", "~"))


async def test_interactive_editor_runtime_handles_bracketed_paste(app_components):
    """THE LIVE EDITOR SHOULD ACCEPT BRACKETED PASTE INPUT WITHOUT CRASHING."""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)
    payload = "x" * editor.BULK_EDIT_SIZE_THRESHOLD

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            task = asyncio.create_task(editor.run_async())

            await asyncio.sleep(0.05)
            pipe_input.send_text(f"\x1b[200~{payload}\x1b[201~")

            for _ in range(20):
                if editor.buffer.text == payload:
                    break
                await asyncio.sleep(0.02)

            assert editor.buffer.text == payload
            assert not editor.expensive_checks_enabled()

            pipe_input.send_text("\x11")  # CTRL+Q
            result = await asyncio.wait_for(task, timeout=1.5)

    assert result is None


async def test_interactive_editor_runtime_paste_preserves_undo_redo_history(
    app_components,
):
    """LIVE PASTE SHOULD LEAVE THE BUFFER WITH A CORRECT UNDO/REDO HISTORY."""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)
    payload = "x" * editor.BULK_EDIT_SIZE_THRESHOLD

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            task = asyncio.create_task(editor.run_async())

            await asyncio.sleep(0.05)
            pipe_input.send_text(f"\x1b[200~{payload}\x1b[201~")

            for _ in range(20):
                if editor.buffer.text == payload:
                    break
                await asyncio.sleep(0.02)

            assert editor.buffer.text == payload

            pipe_input.send_text("\x1a")  # CTRL+Z
            for _ in range(20):
                if editor.buffer.text == "":
                    break
                await asyncio.sleep(0.02)

            assert editor.buffer.text == ""

            editor.buffer.redo()
            assert editor.buffer.text == payload

            pipe_input.send_text("\x11")  # CTRL+Q
            await asyncio.wait_for(task, timeout=1.5)


async def test_interactive_editor_runtime_save_returns_live_buffer(app_components):
    """CTRL+S SHOULD EXIT THE LIVE EDITOR AND RETURN THE CURRENT BUFFER CONTENT."""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            task = asyncio.create_task(editor.run_async())

            await asyncio.sleep(0.05)
            pipe_input.send_text("hello editor")
            pipe_input.send_text("\x13")  # CTRL+S

            result = await asyncio.wait_for(task, timeout=1.5)

    assert result == "hello editor"


async def test_interactive_editor_runtime_paste_replaces_selection(app_components):
    """LIVE BRACKETED PASTE SHOULD REPLACE THE ACTIVE SELECTION INSTEAD OF APPENDING."""
    context, resolver = app_components
    editor = InteractiveEditor("old text", context.indexer, resolver)
    editor.buffer.selection_state = SelectionState(original_cursor_position=0)
    editor.buffer.cursor_position = len(editor.buffer.text)

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            task = asyncio.create_task(editor.run_async())

            await asyncio.sleep(0.05)
            pipe_input.send_text("\x1b[200~fresh\x1b[201~")

            for _ in range(20):
                if editor.buffer.text == "fresh":
                    break
                await asyncio.sleep(0.02)

            assert editor.buffer.text == "fresh"
            assert editor.buffer.selection_state is None

            pipe_input.send_text("\x11")  # CTRL+Q
            await asyncio.wait_for(task, timeout=1.5)


async def test_interactive_editor_runtime_handles_modified_insert_sequences(
    app_components, monkeypatch
):
    """XTERM-STYLE MODIFIED INSERT ESCAPE SEQUENCES SHOULD PASTE THE SYSTEM CLIPBOARD."""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)
    payloads = iter(["shift insert", "ctrl shift insert"])
    monkeypatch.setattr("promptify.ui.bindings.pyperclip.paste", lambda: next(payloads))

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            task = asyncio.create_task(editor.run_async())

            await asyncio.sleep(0.05)
            pipe_input.send_text("\x1b[2;2~")
            for _ in range(20):
                if editor.buffer.text == "shift insert":
                    break
                await asyncio.sleep(0.02)

            assert editor.buffer.text == "shift insert"

            pipe_input.send_text("\x1b[2;6~")
            for _ in range(20):
                if editor.buffer.text == "shift insertctrl shift insert":
                    break
                await asyncio.sleep(0.02)

            assert editor.buffer.text == "shift insertctrl shift insert"

            pipe_input.send_text("\x11")  # CTRL+Q
            await asyncio.wait_for(task, timeout=1.5)


async def test_interactive_editor_completer_surfaces_full_ranked_path_results(
    app_components,
):
    """THE LIVE EDITOR COMPLETER SHOULD EXPOSE THE FULL, PRETTY PATH RESULT SET."""
    context, resolver = app_components
    for idx in range(20):
        rel_path = f"src/file_{idx:02d}.py"
        context.indexer.files_by_rel[rel_path] = context.indexer.files_by_rel["app.py"].__class__(
            path=context.target_dir / rel_path,
            rel_path=rel_path,
            ext="py",
            size=1,
            mtime=1.0,
        )

    editor = InteractiveEditor("", context.indexer, resolver)
    editor.buffer.text = "<@file:file_"
    editor.buffer.cursor_position = len(editor.buffer.text)

    completions = list(
        editor.buffer.completer.get_completions(
            editor.buffer.document, CompleteEvent(completion_requested=True)
        )
    )

    assert len(completions) == 20
    assert completions[0].display_text == "file_00.py"
    assert completions[0].display_meta_text == "src"

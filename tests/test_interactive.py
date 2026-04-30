"""
UNIT TESTS EXERCISING THE RUNTIME INTERACTIVE EDITOR SURFACE.
"""

import asyncio
from typing import Any, cast

import pytest
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import CompletionState
from prompt_toolkit.completion import CompleteEvent, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.output.base import DummyOutput
from prompt_toolkit.selection import SelectionState

from promptify.ui.bindings import setup_keybindings
from promptify.ui.editor import InteractiveEditor
from promptify.core.terminal import detect_terminal_profile
from promptify.utils.i18n import get_string

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
    assert bindings.get_bindings_for_keys((Keys.ControlF,))


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
        context.indexer.files_by_rel[rel_path] = context.indexer.files_by_rel[
            "app.py"
        ].__class__(
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


async def test_interactive_completion_menu_respects_available_width(app_components):
    """THE COMPLETION MENU SHOULD CLAMP ITS PREFERRED WIDTH TO THE VIEWPORT."""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)
    completions = [
        Completion(
            "src/really_long_path_name.py",
            display="really_long_path_name.py",
            display_meta="some/deeply/nested/path/segment",
        )
    ]
    editor.buffer.complete_state = CompletionState(
        editor.buffer.document,
        completions=completions,
        complete_index=0,
    )

    control = cast(Any, editor.completions_menu.content).content
    app = type("AppStub", (), {"current_buffer": editor.buffer})()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("promptify.ui.editor.get_app", lambda: app)
        assert control.preferred_width(24) == 24
        assert control.preferred_width(40) < control.preferred_width(80)
        assert control.preferred_width(80) <= 57

        medium_content = control.create_content(width=40, height=1)
        medium_line = "".join(text for _, text in medium_content.get_line(0))
        assert "name.py" in medium_line
        assert "segment" in medium_line

        narrow_content = control.create_content(width=20, height=1)
        narrow_line = "".join(text for _, text in narrow_content.get_line(0))
        assert "name.py" in narrow_line
        assert "some/" not in narrow_line


async def test_interactive_overlay_windows_use_responsive_dimensions(app_components):
    """HELP AND ERROR PANELS SHOULD SCALE VIA MIN/MAX BOUNDS INSTEAD OF FIXED SIZES."""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)

    help_width = cast(Dimension, editor.help_window.width)
    help_height = cast(Dimension, editor.help_window.height)
    err_width = cast(Dimension, editor.err_window.width)
    err_height = cast(Dimension, editor.err_window.height)

    assert help_width.weight == 1
    assert help_width.min == 40
    assert help_width.max == 160
    assert help_height.weight == 1
    assert err_width.weight == 1
    assert err_width.min == 28
    assert err_width.max == 96
    assert err_height.weight == 1


async def test_interactive_editor_runtime_search_opens_and_closes_cleanly(
    app_components,
):
    """SEARCH SHOULD OPEN AND CLOSE WITHOUT LEAVING FOCUS OR STATE STUCK."""
    context, resolver = app_components
    editor = InteractiveEditor("alpha beta alpha", context.indexer, resolver)

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            task = asyncio.create_task(editor.run_async())

            await asyncio.sleep(0.05)
            editor.open_search()

            assert editor.search_visible
            assert get_app().current_buffer is editor.search_buffer

            editor.close_search()

            assert not editor.search_visible
            assert get_app().current_buffer is editor.buffer

            pipe_input.send_text("\x11")  # CTRL+Q
            await asyncio.wait_for(task, timeout=1.5)


async def test_interactive_editor_search_step_moves_forward_and_backward(
    app_components,
):
    """SEARCH NAVIGATION SHOULD ADVANCE, REVERSE, AND WRAP PREDICTABLY."""
    context, resolver = app_components
    editor = InteractiveEditor(
        "alpha beta alpha gamma alpha", context.indexer, resolver
    )
    editor.search_buffer.text = "alpha"

    assert editor.search_step(1)
    assert editor.buffer.cursor_position == 0
    assert editor.search_message == ""

    assert editor.search_step(1)
    assert editor.buffer.cursor_position == 11

    assert editor.search_step(-1)
    assert editor.buffer.cursor_position == 0

    editor.buffer.cursor_position = len(editor.buffer.text)
    assert editor.search_step(1)
    assert editor.buffer.cursor_position == 0
    assert editor.search_message == get_string("editor_search_wrapped", "wrapped")


async def test_interactive_editor_runtime_help_returns_focus_to_search(
    app_components,
):
    """HELP SHOULD BE USABLE DURING SEARCH AND RESTORE FOCUS TO THE SEARCH BAR."""
    context, resolver = app_components
    editor = InteractiveEditor("alpha beta alpha", context.indexer, resolver)

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            task = asyncio.create_task(editor.run_async())

            await asyncio.sleep(0.05)
            editor.open_search()

            assert editor.search_visible
            assert get_app().current_buffer is editor.search_buffer

            editor.open_help()

            assert editor.help_visible

            editor.close_help()

            assert not editor.help_visible
            assert get_app().current_buffer is editor.search_buffer

            pipe_input.send_text("\x11")  # CTRL+Q
            await asyncio.wait_for(task, timeout=1.5)


async def test_interactive_editor_runtime_search_selection_clears_on_navigation(
    app_components,
):
    """SEARCH FIELD SELECTION SHOULD CLEAR AFTER PLAIN CURSOR MOVEMENT."""
    context, resolver = app_components
    editor = InteractiveEditor("alpha beta alpha", context.indexer, resolver)

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            task = asyncio.create_task(editor.run_async())

            await asyncio.sleep(0.05)
            editor.open_search()
            pipe_input.send_text("alpha")

            for _ in range(20):
                if editor.search_buffer.text == "alpha":
                    break
                await asyncio.sleep(0.02)

            pipe_input.send_text("\x01")  # CTRL+A
            for _ in range(20):
                if editor.search_buffer.selection_state is not None:
                    break
                await asyncio.sleep(0.02)

            assert editor.search_buffer.selection_state is not None

            pipe_input.send_text("\x1b[C")  # RIGHT
            for _ in range(20):
                if editor.search_buffer.selection_state is None:
                    break
                await asyncio.sleep(0.02)

            assert editor.search_buffer.selection_state is None

            pipe_input.send_text("\x11")  # CTRL+Q
            await asyncio.wait_for(task, timeout=1.5)


async def test_interactive_editor_search_status_reports_active_match_counts(
    app_components,
):
    """SEARCH STATUS SHOULD REPORT THE ACTIVE MATCH ORDINAL AND TOTAL MATCHES."""
    context, resolver = app_components
    editor = InteractiveEditor(
        "alpha beta alpha gamma alpha", context.indexer, resolver
    )
    editor.search_visible = True
    editor.search_buffer.text = "alpha"

    state = editor._get_search_highlight_state()

    assert state is not None
    assert state.matches == (0, 11, 23)
    assert state.active_ordinal == 1
    assert editor._get_search_label_text() == (
        " " + get_string("editor_search_label", "SEARCH") + " "
    )
    assert editor._get_mode_text() == (
        " [ " + get_string("editor_mode_search", "search") + " ] "
    )
    assert editor._get_search_status_text().strip() == get_string(
        "editor_search_status_count", "{current} of {total}"
    ).format(current=1, total=3)


async def test_interactive_editor_search_reuses_session_history(app_components):
    """REOPENING SEARCH SHOULD PREFILL AND CYCLE RECENT SESSION QUERIES."""
    context, resolver = app_components
    editor = InteractiveEditor("alpha beta alpha", context.indexer, resolver)
    editor.search_visible = True
    editor.search_buffer.text = "alpha"

    assert editor.search_step(1)

    editor.close_search()
    editor.search_buffer.text = ""
    editor.open_search()
    assert editor.search_buffer.text == "alpha"

    editor.search_buffer.text = "beta"
    assert editor.search_step(1)

    editor.open_search()
    assert editor.search_buffer.text == "alpha"


async def test_interactive_editor_help_restores_search_cursor_and_selection(
    app_components,
):
    """HELP SHOULD RESTORE THE SEARCH FIELD CURSOR AND SELECTION EXACTLY."""
    context, resolver = app_components
    editor = InteractiveEditor("alpha beta alpha", context.indexer, resolver)
    editor.search_visible = True
    editor.search_buffer.document = Document("alpha", cursor_position=2)
    editor.search_buffer.selection_state = SelectionState(original_cursor_position=0)

    editor.open_help()
    editor.search_buffer.cursor_position = 0
    editor.search_buffer.selection_state = None
    editor.close_help()

    assert editor.search_buffer.cursor_position == 2
    assert editor.search_buffer.selection_state is not None
    assert editor.search_buffer.selection_state.original_cursor_position == 0


async def test_interactive_editor_erases_screen_when_done(app_components, monkeypatch):
    """THE EDITOR SHOULD ASK PROMPT-TOOLKIT TO ERASE ITS UI WHEN THE APP EXITS."""
    context, resolver = app_components
    editor = InteractiveEditor("", context.indexer, resolver)
    observed: dict[str, object] = {}

    class FakeApplication:
        def __init__(self, **kwargs):
            observed.update(kwargs)
            self.layout = kwargs["layout"]
            self.ttimeoutlen = 0.0

        async def run_async(self):
            return None

    monkeypatch.setattr("promptify.ui.editor.Application", FakeApplication)

    result = await editor.run_async()

    assert result is None
    assert observed["erase_when_done"] is True


async def test_interactive_editor_toolbar_and_token_status_follow_mode(
    app_components,
):
    """THE STATUS STRIP SHOULD REFLECT SEARCH AND BUSY STATES CHEAPLY."""
    context, resolver = app_components
    editor = InteractiveEditor("alpha", context.indexer, resolver)

    assert "find" in editor._get_toolbar_text()
    assert editor._get_token_status_text().endswith("  ")

    editor.search_visible = True
    assert "next" in editor._get_toolbar_text()

    editor._token_estimate_busy = True
    assert editor._get_token_status_text().endswith("* ")


async def test_interactive_editor_lexer_flags_incomplete_project_mentions(
    app_components,
):
    """INCOMPLETE PROJECT MENTIONS SHOULD BE TREATED AS INVALID SYNTAX."""
    context, resolver = app_components
    editor = InteractiveEditor("[@proj", context.indexer, resolver)
    lexer = cast(Any, editor.main_window.content).lexer

    if lexer is None:
        pytest.skip("pygments lexer unavailable")

    tokens = lexer.lex_document(Document("[@proj"))(0)
    assert any("invalid-syntax" in style for style, _ in tokens)


async def test_interactive_editor_lexer_flags_unclosed_code_fences(
    app_components,
):
    """THE LAST UNMATCHED CODE FENCE SHOULD BE MARKED AS INVALID SYNTAX."""
    context, resolver = app_components
    editor = InteractiveEditor("```py\nprint('x')\n", context.indexer, resolver)
    lexer = cast(Any, editor.main_window.content).lexer

    if lexer is None:
        pytest.skip("pygments lexer unavailable")

    tokens = lexer.lex_document(Document("```py\nprint('x')\n"))(0)
    assert any("invalid-syntax" in style for style, _ in tokens)


async def test_interactive_editor_lexer_distinguishes_unresolved_references(
    app_components,
):
    """MISSING FILE-LIKE REFERENCES SHOULD USE THE UNRESOLVED ISSUE STYLE."""
    context, resolver = app_components
    editor = InteractiveEditor("<@file:missing.py>", context.indexer, resolver)
    lexer = cast(Any, editor.main_window.content).lexer

    if lexer is None:
        pytest.skip("pygments lexer unavailable")

    tokens = lexer.lex_document(Document("<@file:missing.py>"))(0)
    assert any("unresolved-reference" in style for style, _ in tokens)


async def test_interactive_editor_collects_save_issues_for_missing_symbols(
    app_components,
):
    """SAVE-TIME ISSUE COLLECTION SHOULD FLAG SYMBOL LOOKUPS AND JUMP TARGETS."""
    context, resolver = app_components
    editor = InteractiveEditor(
        "<@symbol:app.py:MissingSymbol>", context.indexer, resolver
    )

    issues = await editor.collect_save_issues()

    assert len(issues) == 1
    assert issues[0].style == "unresolved-reference"
    assert "MissingSymbol" in issues[0].message


async def test_interactive_editor_issue_mode_tracks_issue_navigation(
    app_components,
):
    """ISSUE MODE SHOULD JUMP TO ISSUES AND EXPOSE A NAVIGABLE COUNT."""
    context, resolver = app_components
    editor = InteractiveEditor("[@proj\n<@file:missing.py>", context.indexer, resolver)
    issues = await editor.collect_save_issues()

    editor.activate_issue_mode(issues)

    assert editor.issue_mode_active
    assert (
        get_string("editor_issue_overlay", "{title} issue {ordinal} of {total}")
        .format(
            title=get_string("editor_issue_title_syntax", "syntax"),
            ordinal=1,
            total=2,
            line=1,
            column=1,
            message=get_string(
                "issue_incomplete_mention_syntax", "incomplete mention syntax"
            ),
            context_label=get_string("editor_issue_context_label", "context"),
            fragment="[@proj",
            controls=get_string(
                "editor_issue_controls",
                "[Enter/N] next  ^[R/P] prev  [Esc] close",
            ),
        )
        .splitlines()[0]
        in editor.err_buffer.text
    )
    assert (
        get_string("editor_issue_controls", "[Enter/N] next  ^[R/P] prev  [Esc] close")
        in editor.err_buffer.text
    )
    assert editor.buffer.document.cursor_position_row == 0

    assert editor.step_issue(1)
    assert (
        get_string("editor_issue_overlay", "{title} issue {ordinal} of {total}")
        .format(
            title=get_string("editor_issue_title_reference", "reference"),
            ordinal=2,
            total=2,
            line=2,
            column=1,
            message=get_string(
                "issue_file_unresolved", "file '{path}' could not be resolved"
            ).format(path="missing.py"),
            context_label=get_string("editor_issue_context_label", "context"),
            fragment="<@file:missing.py>",
            controls=get_string(
                "editor_issue_controls",
                "[Enter/N] next  ^[R/P] prev  [Esc] close",
            ),
        )
        .splitlines()[0]
        in editor.err_buffer.text
    )
    assert (
        get_string("editor_issue_controls", "[Enter/N] next  ^[R/P] prev  [Esc] close")
        in editor.err_buffer.text
    )
    assert editor.buffer.document.cursor_position_row == 1


async def test_interactive_editor_uses_ascii_eof_markers_for_legacy_cmd(
    app_components,
):
    """LEGACY CMD PROFILES SHOULD AVOID UNICODE EOF INDICATORS."""
    context, resolver = app_components
    legacy_profile = detect_terminal_profile(
        {
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
            "PROMPT": "$P$G",
        },
        override="auto",
    )
    editor = InteractiveEditor(
        "alpha",
        context.indexer,
        resolver,
        terminal_profile=legacy_profile,
    )
    processor = next(
        item
        for item in cast(Any, editor.main_window.content).input_processors
        if item.__class__.__name__ == "EOFNewlineProcessor"
    )

    assert processor.terminal_profile.eof_newline_present == "$"
    assert processor.terminal_profile.eof_newline_missing == "!"

import pytest
from pathlib import Path

from promptify.i18n import strings

pytestmark = pytest.mark.asyncio


class TestPromptifyCore:
    async def test_sandbox_setup(self, app_components):
        """Validates the test sandbox and indexer correctly parsed the demo project."""
        context, resolver = app_components
        assert "app.py" in context.indexer.files_by_rel
        assert "trap.md" in context.indexer.files_by_rel

        # ENSURE .CASEIGNORE CORRECTLY DROPPED THE SECRET KEY
        assert "secret.key" not in context.indexer.files_by_rel

    async def test_line_ranges(self, app_components):
        """Tests `<@file:app.py:2-5>` slice functionality."""
        context, resolver = app_components

        # TEST SPECIFIC RANGE
        result = await resolver.resolve_user("<@file:app.py:2-4>")
        assert "This is line 2" in result
        assert "This is line 4" in result
        assert "This is line 1" not in result
        assert "This is line 5" not in result

        expected_truncation = (
            strings["truncation_notice"]
            .format(prefix="# ", omitted=17, suffix="")
            .strip()
        )
        assert expected_truncation in result

        # TEST "FIRST N" KEYWORD
        result_first = await resolver.resolve_user("<@file:app.py:first 2>")
        assert "This is line 1" in result_first
        assert "This is line 2" in result_first
        assert "This is line 3" not in result_first

    async def test_size_limits(self, app_components):
        """Tests the safeguard against reading excessively large files."""
        context, resolver = app_components

        # MONKEYPATCH THE THRESHOLD TO A TINY SIZE (10 BYTES)
        context.MAX_FILE_SIZE = 10

        result = await resolver.resolve_user("<@file:app.py>")

        expected_err = strings["err_file_too_large"].format(path="app.py").strip()
        assert expected_err in result

    async def test_system_recursive_loop_prevention(self, app_components):
        """
        RESOLVER TEST: Verifies `resolve_system` operates recursively,
        but stops when it detects an infinite loop.
        """
        context, resolver = app_components

        # TRAP.MD CONTAINS `<@FILE:TRAP.MD>`.
        result = await resolver.resolve_system("<@file:trap.md>")

        expected_err = strings["loop_detected"].format(match="<@file:trap.md>").strip()
        assert expected_err in result

        # RECURSIVE RESOLUTION CHECK (IT SHOULD STILL RESOLVE THE OTHER TAG [@PROJECT])
        assert "Folder PATH listing" in result

    async def test_user_single_pass_safety(self, app_components):
        """
        RESOLVER TEST: Verifies `resolve_user` executes only ONE pass.
        User-supplied mentions should not trigger nested file evaluations.
        """
        context, resolver = app_components

        # TRAP.MD CONTAINS `<@FILE:TRAP.MD>`.
        result = await resolver.resolve_user("<@file:trap.md>")

        # THE RAW TEXT SHOULD BE PRESENT, NOT THE LOOP DETECTION COMMENT
        assert "<@file:trap.md>" in result

        # EXTRACT THE BASE STRING WITHOUT FORMATTING TO ENSURE IT'S NOT PRESENT
        loop_str = strings["loop_detected"].split("-")[0].strip()
        assert loop_str not in result

        # THE [@PROJECT] TAG INSIDE THE FILE SHOULD ALSO REMAIN RAW AND UN-EVALUATED
        assert "[@project]" in result
        assert "Folder PATH listing" not in result

    async def test_git_mentions(self, app_components):
        """Tests `<@git:status>` graceful handling in a non-git sandbox."""
        context, resolver = app_components
        result = await resolver.resolve_user("<@git:status>")

        # Validates that it doesn't crash and returns one of the expected states
        assert any(
            state in result
            for state in [
                "error: git not available",
                "working tree clean",
                "git status error",
            ]
        )

    async def test_symbol_mentions(self, app_components):
        """Tests the `<@symbol:path:name>` AST extraction."""
        context, resolver = app_components

        # Inject a function into the sandbox app.py
        app_path = context.target_dir / "app.py"
        with open(app_path, "a") as f:
            f.write("\n\ndef my_func():\n    print('hello')\n")

        await context.indexer.build_index()

        result = await resolver.resolve_user("<@symbol:app.py:my_func>")
        assert "def my_func():" in result
        assert "print('hello')" in result

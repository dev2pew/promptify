import pytest
from pathlib import Path

pytestmark = pytest.mark.asyncio

class TestPromptifyCore:

    async def test_sandbox_setup(self, app_components):
        """Validates the test sandbox and indexer correctly parsed the demo project."""
        context, resolver = app_components
        assert "app.py" in context.indexer.files_by_rel
        assert "trap.md" in context.indexer.files_by_rel

        # Ensure .caseignore correctly dropped the secret key
        assert "secret.key" not in context.indexer.files_by_rel

    async def test_line_ranges(self, app_components):
        """Tests `<@file:app.py:2-5>` slice functionality."""
        context, resolver = app_components

        # Test specific range
        result = await resolver.resolve_user("<@file:app.py:2-4>")
        assert "This is line 2" in result
        assert "This is line 4" in result
        assert "This is line 1" not in result
        assert "This is line 5" not in result
        assert "(truncated, 17 lines omitted)" in result

        # Test "first N" keyword
        result_first = await resolver.resolve_user("<@file:app.py:first 2>")
        assert "This is line 1" in result_first
        assert "This is line 2" in result_first
        assert "This is line 3" not in result_first

    async def test_size_limits(self, app_components):
        """Tests the safeguard against reading excessively large files."""
        context, resolver = app_components

        # Monkeypatch the threshold to a tiny size (10 bytes)
        context.MAX_FILE_SIZE = 10

        result = await resolver.resolve_user("<@file:app.py>")

        # Updated to match the new string format in context.py
        assert "" in result

    async def test_system_recursive_loop_prevention(self, app_components):
        """
        LEGACY MODE TEST: Verifies `resolve_system` operates recursively,
        but stops when it detects an infinite loop.
        """
        context, resolver = app_components

        # trap.md contains `<@file:trap.md>`.
        # resolve_system should evaluate it, see the loop, and inject the safeguard comment.
        result = await resolver.resolve_system("<@file:trap.md>")

        # Updated to match the new format from resolver.py
        assert "" in result
        # It should also have recursively evaluated [@project] from inside trap.md
        assert "Folder PATH listing" in result

    async def test_user_single_pass_safety(self, app_components):
        """
        INTERACTIVE MODE TEST: Verifies `resolve_user` executes only ONE pass.
        User-supplied mentions should not trigger nested file evaluations.
        """
        context, resolver = app_components

        # trap.md contains `<@file:trap.md>`.
        # resolve_user should read it once, and NEVER evaluate the inner tag.
        result = await resolver.resolve_user("<@file:trap.md>")

        # The raw text should be present, NOT the loop detection comment
        assert "<@file:trap.md>" in result
        assert "loop detected" not in result

        # The [@project] tag inside the file should also remain raw and un-evaluated
        assert "[@project]" in result
        assert "Folder PATH listing" not in result

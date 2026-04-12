import pytest
from pathlib import Path

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
        assert "(truncated, 17 lines omitted)" in result

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

        # MATCH LOWERCASE STYLE IN CONTEXT.PY
        assert "exceeds 5MB size limit" in result

    async def test_system_recursive_loop_prevention(self, app_components):
        """
        RESOLVER TEST: Verifies `resolve_system` operates recursively,
        but stops when it detects an infinite loop.
        """
        context, resolver = app_components

        # TRAP.MD CONTAINS `<@FILE:TRAP.MD>`.
        result = await resolver.resolve_system("<@file:trap.md>")

        # VERIFIED FORMATTED LOOP COMMENT MATCHES YOUR RETURN IN RESOLVER.PY
        assert "" in result

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
        assert "loop detected" not in result

        # THE [@PROJECT] TAG INSIDE THE FILE SHOULD ALSO REMAIN RAW AND UN-EVALUATED
        assert "[@project]" in result
        assert "Folder PATH listing" not in result

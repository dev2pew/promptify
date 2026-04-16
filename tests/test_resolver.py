"""
UNIT TESTS VERIFYING THE RELIABILITY OF THE MENTION EVALUATION ENGINE.
"""

import pytest
from promptify.utils.i18n import strings

pytestmark = pytest.mark.asyncio


async def test_resolve_system_loop(app_components):
    """VERIFIES `RESOLVE_SYSTEM` OPERATES RECURSIVELY, BUT STOPS WHEN IT DETECTS AN INFINITE LOOP."""
    _, resolver = app_components
    res = await resolver.resolve_system("<@file:trap.md>")
    assert (
        strings.get("loop_detected", "loop detected")
        .format(match="<@file:trap.md>")
        .strip()
        in res
    )
    assert "Folder PATH listing" in res  # [@PROJECT] RESOLVED


async def test_resolve_user_single_pass(app_components):
    """VERIFIES `RESOLVE_USER` EXECUTES ONLY ONE PASS TO PREVENT NESTED FILE EVALUATIONS."""
    _, resolver = app_components
    res = await resolver.resolve_user("<@file:trap.md>")
    assert "<@file:trap.md>" in res
    assert (
        strings.get("loop_detected", "loop detected").split("-")[0].strip() not in res
    )
    assert "[@project]" in res


async def test_resolve_various_tags(app_components):
    """TESTS MULTIPLE TAGS RESOLVING CORRECTLY IN A SINGLE PASS VIA THE NEW MODREGISTRY."""
    _, resolver = app_components
    res = await resolver.resolve_user("<@dir:src> <@ext:md> <@tree:src>")
    assert "main.py" in res
    assert "trap.md" in res
    assert "utils.py" in res


async def test_invalid_syntax_highlighting(app_components):
    """TESTS THAT INVALID MENTIONS DO NOT CRASH THE RESOLVER, BUT FALLBACK GRACEFULLY."""
    _, resolver = app_components
    # AN UNCLOSED BRACKET SHOULD SIMPLY NOT RESOLVE AND BE TREATED AS TEXT
    res = await resolver.resolve_user("<@file:missing.py")
    assert "<@file:missing.py" in res

    # A FILE THAT DOESN'T EXIST (WHICH IS VALID SYNTAX BUT INVALID PATH)
    res_not_found = await resolver.resolve_user("<@file:non_existent.py>")
    assert (
        strings.get("err_file_not_found", "file not found").format(
            query="non_existent.py"
        )
        in res_not_found
    )

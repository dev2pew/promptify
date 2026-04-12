import pytest
from promptify.utils.i18n import strings

pytestmark = pytest.mark.asyncio


async def test_resolve_system_loop(app_components):
    """Verifies `resolve_system` operates recursively, but stops when it detects an infinite loop."""
    _, resolver = app_components
    res = await resolver.resolve_system("<@file:trap.md>")
    assert strings["loop_detected"].format(match="<@file:trap.md>").strip() in res
    assert "Folder PATH listing" in res  # [@PROJECT] RESOLVED


async def test_resolve_user_single_pass(app_components):
    """Verifies `resolve_user` executes only ONE pass to prevent nested file evaluations."""
    _, resolver = app_components
    res = await resolver.resolve_user("<@file:trap.md>")
    assert "<@file:trap.md>" in res
    assert strings["loop_detected"].split("-")[0].strip() not in res
    assert "[@project]" in res


async def test_resolve_various_tags(app_components):
    """Tests multiple tags resolving correctly in a single pass."""
    _, resolver = app_components
    res = await resolver.resolve_user("<@dir:src> <@ext:md>")
    assert "main.py" in res
    assert "trap.md" in res

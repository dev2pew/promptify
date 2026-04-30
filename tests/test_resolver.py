"""Tests for the mention resolution engine"""

import pytest
from promptify.utils.i18n import get_string
from promptify.ui.editor import CustomPromptLexer

pytestmark = pytest.mark.asyncio


async def test_resolve_system_loop(app_components):
    """`resolve_system` should recurse while stopping on infinite loops"""
    _, resolver = app_components
    res = await resolver.resolve_system("<@file:trap.md>")
    assert (
        get_string("loop_detected", "loop detected")
        .format(match="<@file:trap.md>")
        .strip()
        in res
    )
    assert "Folder PATH listing" in res  # [@PROJECT] RESOLVED


async def test_resolve_user_single_pass(app_components):
    """`resolve_user` should execute only one pass"""
    _, resolver = app_components
    res = await resolver.resolve_user("<@file:trap.md>")
    assert "<@file:trap.md>" in res
    assert get_string("loop_detected", "loop detected").split("-")[0].strip() not in res
    assert "[@project]" in res


async def test_resolve_various_tags(app_components):
    """Multiple tags should resolve correctly in a single pass"""
    _, resolver = app_components
    res = await resolver.resolve_user("<@dir:src> <@ext:md> <@tree:src>")
    assert "main.py" in res
    assert "trap.md" in res
    assert "utils.py" in res


async def test_invalid_syntax_highlighting(app_components):
    """Invalid mentions should not crash the resolver"""
    _, resolver = app_components
    # AN UNCLOSED BRACKET SHOULD SIMPLY NOT RESOLVE AND BE TREATED AS TEXT
    res = await resolver.resolve_user("<@file:missing.py")
    assert "<@file:missing.py" in res

    # A FILE THAT DOESN'T EXIST (WHICH IS VALID SYNTAX BUT INVALID PATH)
    res_not_found = await resolver.resolve_user("<@file:non_existent.py>")
    assert (
        get_string("err_file_not_found", "file not found").format(
            query="non_existent.py"
        )
        in res_not_found
    )


async def test_file_mentions_outside_project_are_invalid(app_components):
    """Absolute or escaping file queries should be treated as invalid"""
    context, resolver = app_components
    lexer = CustomPromptLexer(resolver.registry, context.indexer, resolver)

    assert not lexer.is_valid_mention("<@file:C:/outside/app.py:10>")
    assert not lexer.is_valid_mention("<@file:../app.py>")


async def test_root_dir_mentions_are_valid(app_components):
    """Root-scoped dir and tree mentions should match resolver behavior"""
    context, resolver = app_components
    lexer = CustomPromptLexer(resolver.registry, context.indexer, resolver)

    assert lexer.is_valid_mention("<@dir:/>")
    assert lexer.is_valid_mention("<@tree:/>")


async def test_symbol_mentions_follow_resolver_validation(app_components):
    """Symbol validation should allow optional symbol parts but reject escapes"""
    context, resolver = app_components
    lexer = CustomPromptLexer(resolver.registry, context.indexer, resolver)

    assert lexer.is_valid_mention("<@symbol:app.py>")
    assert lexer.is_valid_mention("<@symbol:app.py:main>")
    assert not lexer.is_valid_mention("<@symbol:../app.py:main>")


async def test_estimate_tokens_caches_expensive_tree_lookups(
    app_components, monkeypatch
):
    """Tree token estimation should stay exact without repeated rebuilds"""
    context, resolver = app_components
    calls = 0
    original = resolver._estimate_tree_length

    def wrapped(root_rel: str = "", max_depth: int | None = None) -> int:
        nonlocal calls
        calls += 1
        return original(root_rel, max_depth)

    monkeypatch.setattr(resolver, "_estimate_tree_length", wrapped)

    first = await resolver.estimate_tokens("<@tree:src>")
    second = await resolver.estimate_tokens("<@tree:src>")

    assert first == second
    assert calls == 1

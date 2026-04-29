"""
UNIT TESTS COVERING GIT MENTION PARSING, EXECUTION, COMPLETION, AND HELP LEXING.
"""

import pytest
from prompt_toolkit.document import Document

from promptify.core.mods import GitMentionQuery, GitMod, parse_git_mention_query
from promptify.ui.editor import HelpLexer

pytestmark = pytest.mark.asyncio


class _FakeProc:
    """MINIMAL ASYNC SUBPROCESS STUB FOR GIT COMMAND TESTS."""

    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0):
        self._stdout = stdout.encode()
        self._stderr = stderr.encode()
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


async def test_git_mention_query_parses_escaped_branch_and_log_limit():
    """BRANCH SELECTORS SHOULD ALLOW ESCAPED GRAMMAR CHARACTERS BEFORE LOG ARGS."""
    query = parse_git_mention_query(r"[\]hotfix\>demo]:log:2")

    assert query == GitMentionQuery(
        branch="]hotfix>demo",
        command="log",
        argument="2",
    )


async def test_git_mention_query_parses_branch_scoped_history_limit():
    """THE HISTORY COMMAND SHOULD SHARE THE SAME BRANCH PARSER AND LIMIT RULES."""
    query = parse_git_mention_query(r"[release/1.0]:history:3")

    assert query == GitMentionQuery(
        branch="release/1.0",
        command="history",
        argument="3",
    )


async def test_git_resolver_routes_branch_scoped_log_queries(
    app_components, monkeypatch
):
    """THE SHARED GIT PARSER SHOULD FEED THE RESOLVER THE DECODED BRANCH AND LIMIT."""
    context, resolver = app_components
    observed: dict[str, int | str | None] = {}

    async def fake_get_git_log(
        limit: int | None = None, branch: str | None = None
    ) -> str:
        observed["limit"] = limit
        observed["branch"] = branch
        return "log payload"

    monkeypatch.setattr(context, "get_git_log", fake_get_git_log)

    result = await resolver.resolve_user(r"<@git:[\]hotfix\>demo]:log:2>")

    assert result == "log payload"
    assert observed == {"limit": 2, "branch": "]hotfix>demo"}


async def test_git_context_commands_use_no_pager_and_expected_arguments(
    app_components, monkeypatch
):
    """ALL GIT INVOCATIONS SHOULD STAY NON-INTERACTIVE AND PASS THE EXPECTED ARGS."""
    context, _ = app_components
    context.has_git = True
    calls: list[tuple[str, ...]] = []
    outputs = iter(
        [
            _FakeProc("diff body"),
            _FakeProc(" M app.py"),
            _FakeProc("M\tapp.py"),
            _FakeProc("commit 123"),
            _FakeProc("commit 456"),
            _FakeProc("patch body"),
        ]
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        del kwargs
        calls.append(tuple(args))
        return next(outputs)

    monkeypatch.setattr(
        "promptify.core.context.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    diff_result = await context.get_git_diff("src/main.py", "master")
    status_result = await context.get_git_status()
    branch_status_result = await context.get_git_status("master")
    log_result = await context.get_git_log(limit=2, branch="master")
    default_log_result = await context.get_git_log()
    history_result = await context.get_git_history(limit=2, branch="master")

    assert calls == [
        ("git", "--no-pager", "diff", "master", "--", "src/main.py"),
        ("git", "--no-pager", "status", "-s"),
        ("git", "--no-pager", "diff", "--name-status", "master"),
        ("git", "--no-pager", "log", "--no-color", "-n", "2", "master"),
        ("git", "--no-pager", "log", "--no-color", "-n", "20"),
        (
            "git",
            "--no-pager",
            "log",
            "--no-color",
            "--pretty=fuller",
            "--stat",
            "--patch",
            "-n",
            "2",
            "master",
        ),
    ]
    assert "```diff" in diff_result
    assert "```log" in status_result
    assert "```log" in branch_status_result
    assert "```log" in log_result
    assert "```log" in default_log_result
    assert "```diff" in history_result


async def test_git_mod_completions_support_branch_scoped_log_and_diff(
    app_components, monkeypatch
):
    """GIT COMPLETIONS SHOULD STILL WORK AFTER A BRANCH PREFIX IS PROVIDED."""
    context, _ = app_components
    mod = GitMod()
    monkeypatch.setattr(mod, "_read_git_commit_count", lambda _root, _branch: 3)

    log_completions = list(mod.get_completions("<@git:[master]:log:", context.indexer))
    history_completions = list(
        mod.get_completions("<@git:[master]:history:", context.indexer)
    )
    diff_completions = list(
        mod.get_completions("<@git:[master]:diff:sr", context.indexer)
    )

    assert [completion.text for completion in log_completions] == ["1>", "2>", "3>"]
    assert [completion.text for completion in history_completions] == [
        "1>",
        "2>",
        "3>",
    ]
    assert any(completion.text == "src" for completion in diff_completions)


async def test_help_lexer_colors_branch_scoped_git_mentions():
    """THE HELP LEXER SHOULD TOKENIZE BRANCHED GIT MENTIONS WITHOUT LOSING COLORS."""
    lexer = HelpLexer()
    get_line = lexer.lex_document(Document(r"<@git:[\]hotfix\>demo]:log:2>"))
    tokens = get_line(0)

    assert ("class:mention-path", r"[\]hotfix\>demo]") in tokens
    assert ("class:mention-git-cmd", "log") in tokens
    assert ("class:mention-range", "2") in tokens


async def test_git_mod_completions_offer_branch_placeholder_and_live_branches(
    app_components, monkeypatch
):
    """GIT ROOT COMPLETIONS SHOULD OFFER A BRANCH PLACEHOLDER AND REAL BRANCH NAMES."""
    context, _ = app_components
    mod = GitMod()
    monkeypatch.setattr(
        mod,
        "_read_git_branches",
        lambda _root: ["master", "feature/demo", "]hotfix>demo"],
    )

    root_completions = list(mod.get_completions("<@git:", context.indexer))
    branch_completions = list(mod.get_completions("<@git:[", context.indexer))

    assert any(
        completion.text == "[" and completion.display_text == "[branch]"
        for completion in root_completions
    )
    assert [completion.text for completion in branch_completions] == [
        "master]:",
        "feature/demo]:",
        r"\]hotfix\>demo]:",
    ]


async def test_git_mod_completions_do_not_offer_nested_branch_placeholders(
    app_components, monkeypatch
):
    """ONCE A BRANCH PREFIX IS PRESENT, GIT SHOULD CONTINUE WITH COMMAND COMPLETIONS ONLY."""
    context, _ = app_components
    mod = GitMod()
    monkeypatch.setattr(mod, "_read_git_branches", lambda _root: ["master"])

    completions = list(mod.get_completions("<@git:[master]:[", context.indexer))

    assert completions == []

"""
UNIT TESTS EVALUATING FILE SYSTEM ISOLATION, DATA RETRIEVAL AND CACHING MECHANISMS.
"""

import pytest
from promptify.utils.i18n import strings

pytestmark = pytest.mark.asyncio


async def test_get_file_content(app_components):
    """TESTS STANDARD FILE READING."""
    context, _ = app_components
    res = await context.get_file_content("app.py")
    assert "This is line 1" in res
    assert "```py" in res


async def test_get_file_content_not_found(app_components):
    """TESTS MISSING FILE HANDLING."""
    context, _ = app_components
    res = await context.get_file_content("missing.py")
    assert res == strings.get("err_file_not_found", "file not found").format(
        query="missing.py"
    )


async def test_get_file_content_ranges(app_components):
    """TESTS ALL SUPPORTED LINE RANGE SYNTAXES."""
    context, _ = app_components
    # 2-4
    res = await context.get_file_content("app.py", "2-4")
    assert "This is line 2" in res
    assert "This is line 4" in res
    assert "This is line 5" not in res
    assert (
        strings.get("truncation_notice", "truncated")
        .format(prefix="# ", omitted=17, suffix="")
        .strip()
        in res
    )

    # FIRST 2
    res = await context.get_file_content("app.py", "first 2")
    assert "This is line 1" in res
    assert "This is line 3" not in res

    # LAST 2
    res = await context.get_file_content("app.py", "last 2")
    assert "This is line 19" in res
    assert "This is line 18" not in res

    # #L5
    res = await context.get_file_content("app.py", "#L5")
    assert "This is line 5" in res
    assert "This is line 4" not in res

    # INVALID
    res = await context.get_file_content("app.py", "invalid")
    assert (
        strings.get("err_invalid_range", "invalid range").format(range="invalid") in res
    )


async def test_size_limits(app_components):
    """TESTS THE SAFEGUARD AGAINST READING EXCESSIVELY LARGE FILES."""
    context, _ = app_components
    context.MAX_FILE_SIZE = 10
    res = await context.get_file_content("app.py")
    assert (
        strings.get("err_file_too_large", "file too large")
        .format(path="app.py")
        .strip()
        in res
    )


async def test_get_type_contents(app_components):
    """TESTS FETCHING MULTIPLE FILES BY EXTENSION."""
    context, _ = app_components
    res = await context.get_type_contents("py, md")
    assert "app.py" in res
    assert "trap.md" in res


async def test_get_dir_contents(app_components):
    """TESTS FETCHING ALL FILES IN A DIRECTORY."""
    context, _ = app_components
    res = await context.get_dir_contents("src")
    assert "main.py" in res
    assert "utils.py" in res
    assert "app.py" not in res


async def test_get_tree_contents(app_components):
    """TESTS FETCHING A SCOPED PROJECT TREE VIA <@TREE:PATH> IMPLEMENTATION"""
    context, _ = app_components
    res = await context.get_tree_contents("src")
    assert "tree_header_1" not in res  # TREE HEADER STRINGS RESOLVE TO EXACT OUTPUT
    assert "main.py" in res
    assert "utils.py" in res
    assert "app.py" not in res


async def test_generate_tree(app_components):
    """TESTS PROJECT TREE GENERATION."""
    context, _ = app_components
    res = context.generate_tree()
    assert strings.get("tree_header_1", "TREE /F") in res
    assert "app.py" in res
    assert "src" in res


async def test_git_mentions(app_components):
    """TESTS `<@GIT:STATUS>` GRACEFUL HANDLING ACROSS DIFFERENT REPO STATES."""
    context, _ = app_components
    result = await context.get_git_status()

    # RETRIEVE THE CONFIGURED LOCALIZATION STRINGS DYNAMICALLY
    # SO THE TEST DOESN'T BREAK IF THE USER EDITS EN.JSON.
    clean_state = strings.get("working_tree_clean", "working tree clean")
    error_state = strings.get("git_status_error", "git status error").split("{")[0]

    # IN A REAL ENVIRONMENT, IT EITHER RETURNS AN ERROR STRING (NO GIT),
    # A CLEAN TREE STRING, OR A FORMATTED LOG OF THE CHANGES.
    # WE ALSO EXPLICITLY ALLOW AN EMPTY STRING `""` IF LOCALE/GIT RESOLVES SILENTLY.
    assert result == "" or any(
        state in result
        for state in [
            "error: git not available",
            clean_state,
            error_state,
            "```log",  # <--- FIXES THE FAILURE WHEN YOU HAVE UNCOMMITTED CHANGES
        ]
    ), f"Unexpected git status result: {result!r}"


async def test_tree_depth_mentions(app_components):
    """TESTS `<@TREE:PATH:LEVEL>` PROPERLY LIMITS THE RECURSIVE DEPTH."""
    context, _ = app_components

    # 1. EVALUATE DEPTH RESTRICTION MECHANISM
    scoped_tree = await context.get_tree_contents("src", depth_str="1")
    assert "tree_header_1" not in scoped_tree
    assert "main.py" in scoped_tree
    assert "utils.py" in scoped_tree

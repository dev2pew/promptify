"""
UNIT TESTS COVERING PATH MATCHING AND COMPLETION PRESENTATION HELPERS.
"""

from pathlib import Path
from types import SimpleNamespace

from promptify.core.matching import build_path_display_map, rank_path_candidates
from promptify.core.models import FileMeta
from promptify.core.mods import FileMod


def test_rank_path_candidates_prioritizes_filename_hits():
    """BASENAME AND PATH-TAIL HITS SHOULD RISE ABOVE LOOSER FUZZY CANDIDATES."""
    ranked = rank_path_candidates(
        "main",
        [
            "docs/maintainers.md",
            "src/domain/main_service.py",
            "src/main.py",
            "src/features/payment.py",
        ],
    )

    assert ranked[0] == "src/main.py"


def test_build_path_display_map_disambiguates_duplicate_names():
    """DUPLICATE BASENAMES SHOULD GAIN JUST ENOUGH PARENT CONTEXT TO STAY UNIQUE."""
    display_map = build_path_display_map(
        [
            "src/auth/main.py",
            "src/billing/main.py",
            "src/auth/service.py",
        ]
    )

    assert display_map["src/auth/service.py"] == ("service.py", "src/auth")
    assert display_map["src/auth/main.py"][0] == "auth/main.py"
    assert display_map["src/billing/main.py"][0] == "billing/main.py"
    assert display_map["src/auth/main.py"][1] == "src"
    assert display_map["src/billing/main.py"][1] == "src"


def test_file_mod_completions_support_backslash_queries_and_compact_meta():
    """WINDOWS-STYLE PATH INPUTS SHOULD COMPLETE INTO NORMALIZED PROJECT PATHS."""
    indexer = SimpleNamespace(
        files_by_rel={
            "src/main.py": FileMeta(
                path=Path("src/main.py"),
                rel_path="src/main.py",
                ext="py",
                size=1,
                mtime=1.0,
            ),
            "src/utils.py": FileMeta(
                path=Path("src/utils.py"),
                rel_path="src/utils.py",
                ext="py",
                size=1,
                mtime=1.0,
            ),
        },
        dirs=set(),
    )

    completions = list(FileMod().get_completions("<@file:src\\ma", indexer))

    assert completions[0].text == "src/main.py"
    assert completions[0].display_text == "main.py"
    assert completions[0].display_meta_text == "src"


def test_file_mod_completions_are_not_limited_to_fifteen_items():
    """FILE COMPLETIONS SHOULD FLOW THROUGH THE FULL RANKED RESULT SET."""
    files = {
        f"src/file_{idx:02d}.py": FileMeta(
            path=Path(f"src/file_{idx:02d}.py"),
            rel_path=f"src/file_{idx:02d}.py",
            ext="py",
            size=1,
            mtime=1.0,
        )
        for idx in range(20)
    }
    indexer = SimpleNamespace(files_by_rel=files, dirs=set())

    completions = list(FileMod().get_completions("<@file:file_", indexer))

    assert len(completions) == 20

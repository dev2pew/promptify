"""Tests for path matching and completion presentation helpers"""

from pathlib import Path
from typing import cast

from promptify.core.indexer import ProjectIndexer
from promptify.core.matching import build_path_display_map, rank_path_candidates
from promptify.core.models import FileMeta
from promptify.core.mods import DirMod, FileMod


class IndexerStub:
    """Minimal indexer shape used by completion tests"""

    def __init__(self, files_by_rel: dict[str, FileMeta], dirs: set[str]):
        self.files_by_rel = files_by_rel
        self.dirs = dirs


def test_rank_path_candidates_prioritizes_filename_hits():
    """Filename and path-tail hits should outrank looser fuzzy matches"""
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
    """Duplicate basenames should gain enough parent context to stay unique"""
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
    """Windows-style paths should complete into normalized project paths"""
    indexer = IndexerStub(
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

    completions = list(
        FileMod().get_completions("<@file:src\\ma", cast(ProjectIndexer, indexer))
    )

    assert completions[0].text == "src/main.py"
    assert completions[0].display_text == "main.py"
    assert completions[0].display_meta_text == "src"


def test_file_mod_completions_are_not_limited_to_fifteen_items():
    """File completions should include the full ranked result set"""
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
    indexer = IndexerStub(files_by_rel=files, dirs=set())

    completions = list(
        FileMod().get_completions("<@file:file_", cast(ProjectIndexer, indexer))
    )

    assert len(completions) == 20


def test_file_mod_exact_match_helpers_do_not_show_path_meta():
    """Exact-match helpers should not repeat directory metadata"""
    indexer = IndexerStub(
        files_by_rel={
            "src/main.py": FileMeta(
                path=Path("src/main.py"),
                rel_path="src/main.py",
                ext="py",
                size=1,
                mtime=1.0,
            )
        },
        dirs=set(),
    )

    completions = list(
        FileMod().get_completions("<@file:src/main.py", cast(ProjectIndexer, indexer))
    )

    assert completions[0].display_text == "main.py>"
    assert completions[0].display_meta_text == ""
    assert completions[1].display_text == "main.py:"
    assert completions[1].display_meta_text == ""


def test_dir_mod_completions_do_not_show_path_meta():
    """Directory completions should keep the menu lightweight and label-only"""
    indexer = IndexerStub(
        files_by_rel={},
        dirs={"src/features/auth", "src/features/billing"},
    )

    completions = list(
        DirMod().get_completions("<@dir:auth", cast(ProjectIndexer, indexer))
    )

    assert completions[0].display_meta_text == ""

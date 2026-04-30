"""Tests for real-time directory watching and index updates"""

import pytest
from watchdog.events import FileCreatedEvent, FileDeletedEvent

pytestmark = pytest.mark.asyncio


async def test_indexer_build(app_components):
    """The indexer should build the expected initial file tree"""
    context, _ = app_components
    indexer = context.indexer
    assert "app.py" in indexer.files_by_rel
    assert "src/main.py" in indexer.files_by_rel
    assert "secret.key" not in indexer.files_by_rel
    assert "test.log" not in indexer.files_by_rel


async def test_indexer_find_matches(app_components):
    """The indexer should support exact, glob, and fuzzy matching"""
    context, _ = app_components
    indexer = context.indexer
    # EXACT
    assert len(indexer.find_matches("app.py")) == 1
    assert indexer.find_matches("src\\main.py")[0].rel_path == "src/main.py"
    # GLOB
    assert len(indexer.find_matches("src/*.py")) == 2
    # FUZZY
    assert indexer.find_matches("main")[0].rel_path == "src/main.py"


async def test_indexer_extensions(app_components):
    """Extension indexing and retrieval should work correctly"""
    context, _ = app_components
    indexer = context.indexer
    exts = indexer.get_all_extensions()
    assert "py" in exts
    assert "md" in exts

    py_files = indexer.get_by_extensions(["py"])
    assert len(py_files) == 3  # APP.PY, SRC/MAIN.PY, SRC/UTILS.PY


async def test_indexer_events(app_components, test_sandbox):
    """Filesystem events should update the index state correctly"""
    context, _ = app_components
    indexer = context.indexer
    demo_dir = test_sandbox["demo"]

    # SIMULATE CREATE
    new_file = demo_dir / "new.py"
    new_file.write_text("print('new')", encoding="utf-8")
    event = FileCreatedEvent(str(new_file))
    indexer.on_any_event(event)
    assert "new.py" in indexer.files_by_rel

    # SIMULATE DELETE
    event = FileDeletedEvent(str(new_file))
    indexer.on_any_event(event)
    assert "new.py" not in indexer.files_by_rel

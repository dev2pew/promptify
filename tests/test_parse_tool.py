"""Tests for the standalone reverse parser under tools/parse.py"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType


def _load_parse_tool() -> ModuleType:
    """Load the standalone parse.py script as a testable module"""
    script_path = Path(__file__).parent.parent / "tools" / "parse.py"
    spec = importlib.util.spec_from_file_location("promptify_parse_tool", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load tools/parse.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_parse_sandbox(name: str) -> Path:
    """Create a repo-local scratch directory for parse tool tests"""
    root = Path(__file__).parent / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_parse_tool_rebuilds_only_file_and_dir_mentions(capsys):
    """Only file and dir mention outputs should be rebuilt from the markdown prompt"""
    parse_tool = _load_parse_tool()
    root = _build_parse_sandbox("sandbox_parse_tool_basic")
    prompt = root / "prompt.md"
    prompt.write_text(
        "\n".join(
            [
                "custom prose",
                "",
                "```py",
                "- `fake.py`",
                "print('leave me alone')",
                "```",
                "",
                "- `src/app.py`",
                "",
                "```py",
                "print('real app')",
                "```",
                "",
                "- `src/app.py:App.run`",
                "",
                "```py",
                "def run():",
                "    pass",
                "```",
                "",
                "- `src/utils.py`",
                "",
                "```py",
                "print('dir output file')",
                "```",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    parse_tool.parse_file(prompt)
    captured = capsys.readouterr()
    output_root = root / "prompt_res"

    assert "2 file(s)" in captured.out
    assert (output_root / "src" / "app.py").read_text(encoding="utf-8") == (
        "print('real app')\n"
    )
    assert (output_root / "src" / "utils.py").read_text(encoding="utf-8") == (
        "print('dir output file')\n"
    )
    assert not (output_root / "fake.py").exists()


def test_parse_tool_warns_and_dedupes_duplicate_mention_outputs(capsys):
    """Duplicate file mentions should warn with both source locations and keep the first"""
    parse_tool = _load_parse_tool()
    root = _build_parse_sandbox("sandbox_parse_tool_duplicates")
    prompt = root / "prompt.md"
    prompt.write_text(
        "\n".join(
            [
                "- `src/app.py`",
                "",
                "```py",
                "print('first copy')",
                "```",
                "",
                "- `src/app.py`",
                "",
                "```py",
                "print('second copy')",
                "```",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stale_root = root / "prompt_res"
    stale_root.mkdir()
    (stale_root / "stale.txt").write_text("old", encoding="utf-8")

    parse_tool.parse_file(prompt)
    captured = capsys.readouterr()

    assert "warning: duplicate mention output for 'src/app.py'" in captured.err
    assert f"{prompt}:1:4" in captured.err
    assert f"{prompt}:7:4" in captured.err
    assert (stale_root / "src" / "app.py").read_text(encoding="utf-8") == (
        "print('first copy')\n"
    )
    assert not (stale_root / "stale.txt").exists()


def test_parse_tool_main_requires_file_arguments():
    """The standalone parser should stay CLI-only and exit with usage on no args"""
    parse_tool = _load_parse_tool()

    assert parse_tool.main(["parse.py"]) == 2

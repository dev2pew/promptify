"""Tests for command-line interface argument mappings"""

import pytest
from promptify.core.cli import parse_cli_args, CLIConfig, extract_help_from_docstring
from promptify.core.config import CaseConfig
from promptify.core.settings import build_settings
from promptify.main import App


def test_docstring_extraction():
    """The dynamic help parser should identify args and descriptions"""
    helps = extract_help_from_docstring(CLIConfig)

    assert "case" in helps
    assert "path" in helps
    assert "mode" in helps
    # VERIFY CONTENT EXISTS AND ISN'T JUST AN EMPTY STRING
    assert len(helps["case"]) > 20
    assert "target project path" in helps["path"].lower()


def test_cli_parsing_basic():
    """Short and long flags should map correctly to the dataclass"""
    # TEST SHORT FLAGS
    args = ["-c", "my_case", "-p", "./src", "-m", "s"]
    config = parse_cli_args(args)
    assert config.case == "my_case"
    assert config.path == "./src"
    assert config.mode == "s"

    # TEST LONG FLAGS
    args = ["--case", "alt_case", "--path", "/tmp", "--mode", "interactive"]
    config = parse_cli_args(args)
    assert config.case == "alt_case"
    assert config.path == "/tmp"
    assert config.mode == "interactive"


def test_cli_argument_order_independence():
    """Argument order should not affect the resulting config"""
    order_a = parse_cli_args(["-m", "s", "-c", "case_a", "-p", "."])
    order_b = parse_cli_args(["-p", ".", "-m", "s", "-c", "case_a"])

    assert order_a == order_b


def test_mode_normalization_logic():
    """
    The parser should accept the supported mode strings.

    The actual normalization happens in `App.run`, but the parser still needs
    to capture the raw values.
    """
    valid_modes = [
        "s",
        "simple",
        "l",
        "legacy",
        "o",
        "old",
        "i",
        "interactive",
        "a",
        "advanced",
        "e",
        "editor",
    ]
    for m in valid_modes:
        config = parse_cli_args(["-m", m])
        assert config.mode == m


def test_cli_default_behavior():
    """Empty arguments should produce `None` values"""
    config = parse_cli_args([])
    assert config.case is None
    assert config.path is None
    assert config.mode is None


def test_programmatic_config_creation():
    """The config dataclass should be instantiable without the parser"""
    config = CLIConfig(case="manual", path="/manual/path", mode="editor")
    assert config.case == "manual"
    assert config.path == "/manual/path"
    assert config.mode == "editor"


@pytest.mark.asyncio
async def test_save_output_uses_case_folder(test_sandbox, monkeypatch):
    """Outputs should be stored under the case folder name"""
    app = App()
    app.outs_dir = test_sandbox["outs"]
    case = CaseConfig(test_sandbox["case"])
    monkeypatch.setattr("promptify.main.pyperclip.copy", lambda _text: None)

    await app.save_output(case, "demo output", raw_content="raw output")

    parent_dir = app.outs_dir / test_sandbox["case"].name
    assert parent_dir.exists()
    assert not (app.outs_dir / case.name).exists()
    assert list(parent_dir.rglob("*.md"))
    assert list(parent_dir.rglob("*.raw"))


@pytest.mark.asyncio
async def test_mode_state_is_persisted_per_case(test_sandbox):
    """Last mode should be stored per case using a unique case key"""
    app = App()
    app.data_dir = test_sandbox["root"] / "data"
    case = CaseConfig(test_sandbox["case"])
    state = await app.get_state()

    await app.save_last_mode(case, 2, state)

    reloaded = await app.get_state()
    assert await app.get_last_mode(case, reloaded) == 2


@pytest.mark.asyncio
async def test_mode_state_uses_unique_case_keys(test_sandbox):
    """Cases with the same display name should not share mode history"""
    app = App()
    app.cases_dir = test_sandbox["root"] / "cases"
    app.data_dir = test_sandbox["root"] / "data"
    state = await app.get_state()

    first_case_dir = test_sandbox["root"] / "cases" / "alpha" / "shared"
    second_case_dir = test_sandbox["root"] / "cases" / "beta" / "shared"
    first_case_dir.mkdir(parents=True)
    second_case_dir.mkdir(parents=True)

    for case_dir in [first_case_dir, second_case_dir]:
        (case_dir / "config.json").write_text(
            '{"name": "shared", "types": ["*"]}', encoding="utf-8"
        )

    first_case = CaseConfig(first_case_dir)
    second_case = CaseConfig(second_case_dir)

    await app.save_last_mode(first_case, 1, state)
    await app.save_last_mode(second_case, 2, state)

    reloaded = await app.get_state()
    assert await app.get_last_mode(first_case, reloaded) == 1
    assert await app.get_last_mode(second_case, reloaded) == 2


@pytest.mark.asyncio
async def test_save_output_respects_behavior_toggles(test_sandbox, monkeypatch):
    """Output persistence should respect raw-save and clipboard toggles"""
    app = App()
    app.outs_dir = test_sandbox["outs"] / "toggle_case"
    case = CaseConfig(test_sandbox["case"])
    settings, _ = build_settings(
        {
            "PROMPTIFY_COPY_OUTPUT_TO_CLIPBOARD": "false",
            "PROMPTIFY_SAVE_RAW_OUTPUT": "false",
        }
    )

    monkeypatch.setattr("promptify.main.APP_SETTINGS", settings)
    monkeypatch.setattr(
        "promptify.main.pyperclip.copy",
        lambda _text: (_ for _ in ()).throw(AssertionError("clipboard should be off")),
    )

    await app.save_output(case, "demo output", raw_content="raw output")

    parent_dir = app.outs_dir / test_sandbox["case"].name
    assert list(parent_dir.rglob("*.md"))
    assert not list(parent_dir.rglob("*.raw"))

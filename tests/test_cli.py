"""
UNIT TESTS VERIFYING COMMAND LINE INTERFACE ARGUMENT MAPPINGS.
"""

import pytest
from promptify.core.cli import parse_cli_args, CLIConfig, extract_help_from_docstring
from promptify.core.config import CaseConfig
from promptify.main import App


def test_docstring_extraction():
    """VERIFIES THE DYNAMIC HELP PARSER CORRECTLY IDENTIFIES ARGS AND DESCRIPTIONS."""
    helps = extract_help_from_docstring(CLIConfig)

    assert "case" in helps
    assert "path" in helps
    assert "mode" in helps
    # VERIFY CONTENT EXISTS AND ISN'T JUST AN EMPTY STRING
    assert len(helps["case"]) > 20
    assert "target project path" in helps["path"].lower()


def test_cli_parsing_basic():
    """VERIFIES MAPPING OF SHORT AND LONG FLAGS TO THE DATACLASS."""
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
    """ENSURES THE ORDER OF ARGUMENTS DOES NOT AFFECT THE RESULTING CONFIG."""
    order_a = parse_cli_args(["-m", "s", "-c", "case_a", "-p", "."])
    order_b = parse_cli_args(["-p", ".", "-m", "s", "-c", "case_a"])

    assert order_a == order_b


def test_mode_normalization_logic():
    """
    VERIFIES THAT THE PARSER ACCEPTS VARIOUS MODE STRINGS.
    (NOTE: THE ACTUAL NORMALIZATION HAPPENS IN APP.RUN, BUT THE PARSER MUST CAPTURE THEM).
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
    """VERIFIES THAT EMPTY ARGUMENTS RESULT IN NONE VALUES, ALLOWING THE APP TO TRIGGER WIZARDS."""
    config = parse_cli_args([])
    assert config.case is None
    assert config.path is None
    assert config.mode is None


def test_programmatic_config_creation():
    """VERIFIES THE DATACLASS CAN BE INSTANTIATED DIRECTLY WITHOUT THE PARSER."""
    config = CLIConfig(case="manual", path="/manual/path", mode="editor")
    assert config.case == "manual"
    assert config.path == "/manual/path"
    assert config.mode == "editor"


@pytest.mark.asyncio
async def test_save_output_uses_case_folder(test_sandbox, monkeypatch):
    """OUTPUTS SHOULD BE STORED UNDER THE CASE FOLDER NAME."""
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
    """LAST MODE SHOULD BE STORED PER CASE USING A UNIQUE CASE KEY."""
    app = App()
    app.data_dir = test_sandbox["root"] / "data"
    case = CaseConfig(test_sandbox["case"])
    state = await app.get_state()

    await app.save_last_mode(case, 2, state)

    reloaded = await app.get_state()
    assert await app.get_last_mode(case, reloaded) == 2


@pytest.mark.asyncio
async def test_mode_state_uses_unique_case_keys(test_sandbox):
    """CASES WITH THE SAME DISPLAY NAME SHOULD NOT SHARE MODE HISTORY."""
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

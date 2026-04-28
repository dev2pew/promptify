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
async def test_save_output_uses_case_parent_folder(test_sandbox, monkeypatch):
    """OUTPUTS SHOULD BE STORED UNDER THE CASE PARENT FOLDER NAME, NOT THE CASE NAME."""
    app = App()
    app.outs_dir = test_sandbox["outs"]
    case = CaseConfig(test_sandbox["case"])
    monkeypatch.setattr("promptify.main.pyperclip.copy", lambda _text: None)

    await app.save_output(case, "demo output", raw_content="raw output")

    case_parent_dir = app.outs_dir / test_sandbox["case"].parent.name
    assert case_parent_dir.exists()
    assert not (app.outs_dir / case.name).exists()
    assert list(case_parent_dir.rglob("*.md"))
    assert list(case_parent_dir.rglob("*.raw"))

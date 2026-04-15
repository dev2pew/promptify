import pytest
from promptify.core.cli import parse_cli_args, CLIConfig, extract_help_from_docstring


def test_docstring_extraction():
    """Verifies the dynamic help parser correctly identifies args and descriptions."""
    helps = extract_help_from_docstring(CLIConfig)

    assert "case" in helps
    assert "path" in helps
    assert "mode" in helps
    # VERIFY CONTENT EXISTS AND ISN'T JUST AN EMPTY STRING
    assert len(helps["case"]) > 20
    assert "target project path" in helps["path"].lower()


def test_cli_parsing_basic():
    """Verifies mapping of short and long flags to the dataclass."""
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
    """Ensures the order of arguments does not affect the resulting config."""
    order_a = parse_cli_args(["-m", "s", "-c", "case_a", "-p", "."])
    order_b = parse_cli_args(["-p", ".", "-m", "s", "-c", "case_a"])

    assert order_a == order_b


def test_mode_normalization_logic():
    """
    Verifies that the parser accepts various mode strings.
    (Note: The actual normalization happens in App.run, but the parser must capture them).
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
    """Verifies that empty arguments result in None values, allowing the App to trigger wizards."""
    config = parse_cli_args([])
    assert config.case is None
    assert config.path is None
    assert config.mode is None


def test_programmatic_config_creation():
    """Verifies the dataclass can be instantiated directly without the parser."""
    config = CLIConfig(case="manual", path="/manual/path", mode="editor")
    assert config.case == "manual"
    assert config.path == "/manual/path"
    assert config.mode == "editor"

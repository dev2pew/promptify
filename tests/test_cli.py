"""Tests for command-line interface argument mappings"""

from typing import Any, cast

import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.shortcuts import PromptSession

from promptify.core.cli import parse_cli_args, CLIConfig, extract_help_from_docstring
from promptify.core.config import CaseConfig
from promptify.core.settings import build_settings
from promptify.main import App
from promptify.ui.logger import (
    Logger,
    PrefixSuggestion,
    _AUTO_SUGGESTION_STYLE,
)


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


def test_prefix_suggestion_only_shows_matching_suffix():
    """Defaults should appear as ghost text only while the typed prefix still matches"""
    suggestion = PrefixSuggestion(r"C:\work\demo")

    empty_suggestion = suggestion.get_suggestion(None, Document(""))
    prefix_suggestion = suggestion.get_suggestion(None, Document(r"C:\w"))

    assert empty_suggestion is not None
    assert empty_suggestion.text == r"C:\work\demo"
    assert prefix_suggestion is not None
    assert prefix_suggestion.text == r"ork\demo"
    assert suggestion.get_suggestion(None, Document(r"C:\work\demo")) is None
    assert suggestion.get_suggestion(None, Document("other")) is None


@pytest.mark.asyncio
async def test_logger_input_async_passes_prefix_suggestion(monkeypatch):
    """Shared input prompts should pass the inline default suggestion through the logger"""
    captured: dict[str, Any] = {}

    class FakeSession:
        async def prompt_async(self, message, **kwargs):
            captured["message"] = message
            captured["kwargs"] = kwargs
            return ""

    logger = Logger()
    logger._session = cast(PromptSession[str], FakeSession())

    result = await logger.input_async("select case", default="demo")

    assert result == ""
    kwargs = cast(dict[str, Any], captured["kwargs"])
    auto_suggest = cast(PrefixSuggestion, kwargs["auto_suggest"])
    de_suggestion = auto_suggest.get_suggestion(None, Document("de"))
    empty_suggestion = auto_suggest.get_suggestion(None, Document(""))

    assert isinstance(auto_suggest, PrefixSuggestion)
    assert de_suggestion is not None
    assert de_suggestion.text == "mo"
    assert empty_suggestion is not None
    assert empty_suggestion.text == "demo"
    assert auto_suggest.get_suggestion(None, Document("x")) is None
    assert kwargs["style"] is logger._input_style
    assert kwargs["key_bindings"] is logger._input_bindings
    assert kwargs["pre_run"] == logger._prime_default_suggestion


def test_logger_styles_auto_suggestion_with_prompt_toolkit_abort_gray():
    """Ghost text should use the same gray prompt-toolkit uses for aborting prompts"""
    logger = Logger()
    attrs = logger._input_style.get_attrs_for_style_str("class:auto-suggestion")

    assert attrs.color == "888888"
    assert logger._input_style.style_rules == [
        ("auto-suggestion", _AUTO_SUGGESTION_STYLE)
    ]


def test_logger_prime_default_suggestion_nudges_empty_buffer():
    """Untouched empty prompts should be nudged once so the suggestion appears immediately"""
    observed: list[str] = []

    class FakeBuffer:
        text = ""

        def insert_text(self, value: str) -> None:
            observed.append(value)

    class FakeSession:
        default_buffer = FakeBuffer()

    logger = Logger()
    logger._session = cast(PromptSession[str], FakeSession())

    logger._prime_default_suggestion()

    assert observed == [""]


def test_logger_tab_binding_accepts_current_suggestion(monkeypatch):
    """Tab should accept the inline suggestion suffix into the current buffer"""

    class FakeBuffer:
        def __init__(self):
            self.suggestion = PrefixSuggestion("demo").get_suggestion(
                None, Document("")
            )
            self.document = Document("")
            self.inserted: list[str] = []

        def insert_text(self, value: str) -> None:
            self.inserted.append(value)

    buffer = FakeBuffer()
    app = type("AppStub", (), {"current_buffer": buffer})()
    logger = Logger()
    monkeypatch.setattr("promptify.ui.logger.get_app", lambda: app)

    bindings = logger._build_input_bindings()
    binding = bindings.get_bindings_for_keys((Keys.Tab,))[0]
    event = cast(KeyPressEvent, type("EventStub", (), {"current_buffer": buffer})())

    assert binding.filter()
    binding.handler(event)
    assert buffer.inserted == ["demo"]


def test_logger_enter_binding_accepts_empty_buffer_suggestion_and_submits(monkeypatch):
    """Enter on an untouched suggested prompt should commit the full value and submit it"""

    class FakeBuffer:
        def __init__(self):
            self.suggestion = PrefixSuggestion("2").get_suggestion(None, Document(""))
            self.document = Document("")
            self.text = ""
            self.inserted: list[str] = []
            self.validated = False

        def insert_text(self, value: str) -> None:
            self.inserted.append(value)
            self.text += value

        def validate_and_handle(self) -> None:
            self.validated = True

    buffer = FakeBuffer()
    app = type("AppStub", (), {"current_buffer": buffer})()
    logger = Logger()
    monkeypatch.setattr("promptify.ui.logger.get_app", lambda: app)

    bindings = logger._build_input_bindings()
    binding = bindings.get_bindings_for_keys((Keys.ControlM,))[0]
    event = cast(KeyPressEvent, type("EventStub", (), {"current_buffer": buffer})())

    assert binding.filter()
    binding.handler(event)
    assert buffer.inserted == ["2"]
    assert buffer.validated is True


@pytest.mark.asyncio
async def test_prompt_with_suggestion_uses_localized_label(monkeypatch):
    """Wizard prompts should keep the label plain and move defaults into suggestions"""
    app = App()
    captured: dict[str, str] = {}

    async def fake_input_async(message: str, default: str = "") -> str:
        captured["message"] = message
        captured["default"] = default
        return ""

    monkeypatch.setattr("promptify.main.log.input_async", fake_input_async)

    result = await app.prompt_with_suggestion(
        "enter_target_path",
        "enter target project path",
        suggested_text=r"C:\demo",
    )

    assert result == ""
    assert captured["message"] == "enter target project path"
    assert captured["default"] == r"C:\demo"


@pytest.mark.asyncio
async def test_case_index_is_persisted_as_list_number(test_sandbox):
    """The remembered case should be stored as the displayed 1-based list number"""
    app = App()
    app.data_dir = test_sandbox["root"] / "data"
    state = await app.get_state()

    await app.save_last_case_index(2, state)

    reloaded = await app.get_state()
    assert await app.get_last_case_index(reloaded, 3) == 2
    assert await app.get_last_case_index(reloaded, 1) is None


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

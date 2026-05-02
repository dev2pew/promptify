"""Tests for environment settings parsing and config fallbacks"""

from promptify.core.settings import build_settings

from _settings_master import get_setting_attr_map


def test_build_settings_accepts_behavior_and_theme_overrides():
    """Valid settings should populate the typed config object"""
    settings, warns = build_settings(
        {
            "PROMPTIFY_MAX_FILE_SIZE": "1234",
            "PROMPTIFY_COPY_OUTPUT_TO_CLIPBOARD": "false",
            "PROMPTIFY_SAVE_RAW_OUTPUT": "no",
            "PROMPTIFY_EDITOR_SHOW_HELP_ON_START": "yes",
            "PROMPTIFY_EDITOR_SHOW_LINE_NUMBERS": "off",
            "PROMPTIFY_EDITOR_WORD_WRAP": "on",
            "PROMPTIFY_THEME_TOPBAR": "bg:#000000 #ffffff",
            "PROMPTIFY_INDEX_WATCH_MODE": "polling",
            "PROMPTIFY_LOG_COLOR_INFO": "ansigreen",
            "PROMPTIFY_TERMINAL_PROFILE": "legacy-cmd",
            "PROMPTIFY_ADVANCED_TOKENIZER": "false",
        }
    )

    assert warns == []
    assert settings.runtime.max_file_size == 1234
    assert not settings.app_behavior.copy_output_to_clipboard
    assert not settings.app_behavior.save_raw_output
    assert settings.editor_behavior.show_help_on_start
    assert not settings.editor_behavior.show_line_numbers
    assert settings.editor_behavior.word_wrap
    assert settings.theme.styles["topbar"] == "bg:#000000 #ffffff"
    assert settings.indexer.watch_mode == "polling"
    assert settings.logger.info_color == "ansigreen"
    assert settings.terminal.profile == "legacy-cmd"
    assert not settings.resolver.advanced_tokenizer_enabled


def test_build_settings_generated_layout_passes_are_applied(settings_pass):
    """Generated settings passes should parse into matching typed values"""
    settings, warns = build_settings(settings_pass.env)

    assert warns == []
    for env_key, section_name, attr_name in get_setting_attr_map():
        section = getattr(settings, section_name)
        assert getattr(section, attr_name) == int(settings_pass.env[env_key])


def test_build_settings_invalid_values_fall_back_and_warn():
    """Invalid settings should fall back safely at import time"""
    settings, warns = build_settings(
        {
            "PROMPTIFY_MAX_FILE_SIZE": "oops",
            "PROMPTIFY_LOG_TIMESTAMPS": "sometimes",
            "PROMPTIFY_INDEX_WATCH_MODE": "broken",
            "PROMPTIFY_TERMINAL_PROFILE": "ansi-art",
            "PROMPTIFY_LOG_COLOR_INFO": "orange",
            "PROMPTIFY_EDITOR_HELP_WIDTH_MIN": "200",
            "PROMPTIFY_EDITOR_HELP_WIDTH_MAX": "50",
            "PROMPTIFY_DEFAULT_IGNORES": "   ",
            "PROMPTIFY_ADVANCED_TOKENIZER": "sometimes",
        }
    )

    assert settings.runtime.max_file_size == 5 * 1024 * 1024
    assert not settings.logger.include_timestamp
    assert settings.indexer.watch_mode == "auto"
    assert settings.terminal.profile == "auto"
    assert settings.logger.info_color == "ansiblue"
    assert settings.resolver.advanced_tokenizer_enabled
    assert settings.editor_layout.help_width_min == 40
    assert settings.editor_layout.help_width_max == 160
    assert settings.runtime.default_ignores == (
        ".git/",
        ".svn/",
        "__pycache__/",
        ".venv/",
        "node_modules/",
    )
    assert len(warns) >= 6

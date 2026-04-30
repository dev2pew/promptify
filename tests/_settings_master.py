"""Centralized test settings baselines and generated pass variants"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import cast
from collections.abc import Mapping, MutableMapping

from dotenv import dotenv_values

DEFAULT_TEST_SETTINGS_PASS_COUNT = 4
TEST_SETTINGS_PASS_COUNT_ENV = "PROMPTIFY_TEST_PASS_COUNT"

_PASS_COUNT_MINIMUM = 1
_EXAMPLE_ENV_PATH = Path(__file__).resolve().parent.parent / ".env.example"
_LAYOUT_KEYS = (
    "PROMPTIFY_UI_TERM_FALLBACK_WIDTH",
    "PROMPTIFY_UI_TERM_FALLBACK_HEIGHT",
    "PROMPTIFY_EDITOR_HELP_WIDTH_MIN",
    "PROMPTIFY_EDITOR_HELP_WIDTH_MAX",
    "PROMPTIFY_EDITOR_HELP_HEIGHT_MIN",
    "PROMPTIFY_EDITOR_HELP_HEIGHT_MAX",
    "PROMPTIFY_EDITOR_ERROR_WIDTH_MIN",
    "PROMPTIFY_EDITOR_ERROR_WIDTH_MAX",
    "PROMPTIFY_EDITOR_ERROR_HEIGHT_MIN",
    "PROMPTIFY_EDITOR_ERROR_HEIGHT_MAX",
)
_SETTING_ATTR_MAP = (
    ("PROMPTIFY_UI_TERM_FALLBACK_WIDTH", "render", "terminal_fallback_width"),
    ("PROMPTIFY_UI_TERM_FALLBACK_HEIGHT", "render", "terminal_fallback_height"),
    ("PROMPTIFY_EDITOR_HELP_WIDTH_MIN", "editor_layout", "help_width_min"),
    ("PROMPTIFY_EDITOR_HELP_WIDTH_MAX", "editor_layout", "help_width_max"),
    ("PROMPTIFY_EDITOR_HELP_HEIGHT_MIN", "editor_layout", "help_height_min"),
    ("PROMPTIFY_EDITOR_HELP_HEIGHT_MAX", "editor_layout", "help_height_max"),
    ("PROMPTIFY_EDITOR_ERROR_WIDTH_MIN", "editor_layout", "err_width_min"),
    ("PROMPTIFY_EDITOR_ERROR_WIDTH_MAX", "editor_layout", "err_width_max"),
    ("PROMPTIFY_EDITOR_ERROR_HEIGHT_MIN", "editor_layout", "err_height_min"),
    ("PROMPTIFY_EDITOR_ERROR_HEIGHT_MAX", "editor_layout", "err_height_max"),
)


@dataclass(frozen=True, slots=True)
class SettingsPass:
    name: str
    env: dict[str, str]


def load_settings_master_env() -> dict[str, str]:
    """Load the documented PROMPTIFY defaults used as the test baseline"""
    raw_values = dotenv_values(_EXAMPLE_ENV_PATH)
    return {
        key: str(value)
        for key, value in raw_values.items()
        if isinstance(key, str)
        and key.startswith("PROMPTIFY_")
        and value is not None
        and key != TEST_SETTINGS_PASS_COUNT_ENV
    }


def install_settings_master_env(
    target_env: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    """Install a deterministic PROMPTIFY env baseline before app imports"""
    resolved_env = os.environ if target_env is None else target_env
    baseline = load_settings_master_env()
    for key, value in baseline.items():
        resolved_env[key] = value
    return baseline


def get_settings_pass_count(env: Mapping[str, str] | None = None) -> int:
    """Read the configurable pass count used by settings-matrix tests"""
    source_env = os.environ if env is None else env
    raw = source_env.get(
        TEST_SETTINGS_PASS_COUNT_ENV, str(DEFAULT_TEST_SETTINGS_PASS_COUNT)
    )
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_TEST_SETTINGS_PASS_COUNT
    return max(_PASS_COUNT_MINIMUM, parsed)


def build_settings_passes(
    count: int | None = None,
    baseline: Mapping[str, str] | None = None,
) -> tuple[SettingsPass, ...]:
    """Generate deterministic layout and render variants for settings tests"""
    source = dict(load_settings_master_env() if baseline is None else baseline)
    pass_count = get_settings_pass_count() if count is None else max(1, count)
    base_width = _get_int(source, "PROMPTIFY_UI_TERM_FALLBACK_WIDTH")
    base_height = _get_int(source, "PROMPTIFY_UI_TERM_FALLBACK_HEIGHT")
    help_width_min = _get_int(source, "PROMPTIFY_EDITOR_HELP_WIDTH_MIN")
    help_width_max = _get_int(source, "PROMPTIFY_EDITOR_HELP_WIDTH_MAX")
    help_height_min = _get_int(source, "PROMPTIFY_EDITOR_HELP_HEIGHT_MIN")
    help_height_max = _get_int(source, "PROMPTIFY_EDITOR_HELP_HEIGHT_MAX")
    err_width_min = _get_int(source, "PROMPTIFY_EDITOR_ERROR_WIDTH_MIN")
    err_width_max = _get_int(source, "PROMPTIFY_EDITOR_ERROR_WIDTH_MAX")
    err_height_min = _get_int(source, "PROMPTIFY_EDITOR_ERROR_HEIGHT_MIN")
    err_height_max = _get_int(source, "PROMPTIFY_EDITOR_ERROR_HEIGHT_MAX")

    passes: list[SettingsPass] = []
    for index in range(pass_count):
        variant = dict(source)
        variant.update(
            {
                "PROMPTIFY_UI_TERM_FALLBACK_WIDTH": str(base_width + (index * 9)),
                "PROMPTIFY_UI_TERM_FALLBACK_HEIGHT": str(base_height + (index * 2)),
                "PROMPTIFY_EDITOR_HELP_WIDTH_MIN": str(help_width_min + (index * 3)),
                "PROMPTIFY_EDITOR_HELP_WIDTH_MAX": str(help_width_max + (index * 11)),
                "PROMPTIFY_EDITOR_HELP_HEIGHT_MIN": str(help_height_min + index),
                "PROMPTIFY_EDITOR_HELP_HEIGHT_MAX": str(help_height_max + (index * 3)),
                "PROMPTIFY_EDITOR_ERROR_WIDTH_MIN": str(err_width_min + (index * 2)),
                "PROMPTIFY_EDITOR_ERROR_WIDTH_MAX": str(err_width_max + (index * 5)),
                "PROMPTIFY_EDITOR_ERROR_HEIGHT_MIN": str(err_height_min + index),
                "PROMPTIFY_EDITOR_ERROR_HEIGHT_MAX": str(err_height_max + (index * 2)),
            }
        )
        passes.append(SettingsPass(name=f"settings-pass-{index + 1}", env=variant))
    return tuple(passes)


def get_layout_keys() -> tuple[str, ...]:
    """Expose the generated layout-related keys for focused assertions"""
    return _LAYOUT_KEYS


def get_setting_attr_map() -> tuple[tuple[str, str, str], ...]:
    """Expose the env-to-settings attribute mapping used by matrix tests"""
    return _SETTING_ATTR_MAP


def _get_int(env: Mapping[str, str], key: str) -> int:
    return int(cast(str, env[key]))

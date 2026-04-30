"""Typed settings and environment-variable parsing for `promptify`"""

from dataclasses import dataclass
import os
from collections.abc import Mapping

from dotenv import load_dotenv

load_dotenv()

_LOG_COLOR_CHOICES = frozenset(
    {
        "ansiblack",
        "ansired",
        "ansigreen",
        "ansiyellow",
        "ansiblue",
        "ansimagenta",
        "ansicyan",
        "ansiwhite",
        "ansigray",
        "ansibrightblack",
        "ansibrightred",
        "ansibrightgreen",
        "ansibrightyellow",
        "ansibrightblue",
        "ansibrightmagenta",
        "ansibrightcyan",
        "ansibrightwhite",
    }
)

_DEFAULT_THEME_STYLES = {
    "topbar": "bg:#333333 #ffffff",
    "topbar-mode": "bg:#333333 #aee6ff bold",
    "topbar-title": "bg:#333333 #00ffff bold",
    "topbar-status": "bg:#333333 #ffd89a",
    "topbar-tokens": "bg:#333333 #ffff00",
    "toolbar": "bg:#333333 #ffffff",
    "toolbar-right": "bg:#333333 #00ff00",
    "completion-menu": "bg:#444444 #ffffff",
    "completion-menu.completion.current": "bg:#1d6f62 #f5fffb bold",
    "editor-frame.border": "fg:#4a4a4a",
    "search-bar": "bg:#1f1f1f #ffffff",
    "search-label": "bg:#1f1f1f #9fe9ff bold",
    "search-input": "bg:#2d2d2d #ffffff",
    "search-status": "bg:#1f1f1f #ffe09c",
    "search-match": "bg:#5d4a1d #fff0cb",
    "search-match-active": "bg:#1f5d8e #f7fbff bold",
    "current-line": "bg:#262a31",
    "err-frame": "bg:#101317",
    "err-frame.border": "fg:#768394",
    "err-frame.label": "bg:#101317 #d7e6f6 bold",
    "err-text": "bg:#171c22 #f2f5f8",
    "mention-tag": "fg:#00ffff bold",
    "mention-path": "fg:#ffaa00",
    "mention-range": "fg:#ff55ff",
    "mention-depth": "fg:#ff55ff",
    "mention-ext": "fg:#ffaa00",
    "mention-git-cmd": "fg:#00aa00",
    "mention-class": "fg:#00ff00 bold",
    "mention-function": "fg:#5555ff",
    "mention-method": "fg:#55ffff",
    "invalid-syntax": "bg:#7c1f24 #fff3f3",
    "unresolved-reference": "bg:#6e4a1c #fff0d8",
    "help-header": "fg:#00ff00 bold",
    "help-key": "fg:#ffff00",
    "trailing-whitespace": "bg:#ff0000",
    "eof-newline": "fg:#ff0000",
}

_THEME_ENV_MAP = {
    "PROMPTIFY_THEME_TOPBAR": "topbar",
    "PROMPTIFY_THEME_TOPBAR_MODE": "topbar-mode",
    "PROMPTIFY_THEME_TOPBAR_TITLE": "topbar-title",
    "PROMPTIFY_THEME_TOPBAR_STATUS": "topbar-status",
    "PROMPTIFY_THEME_TOPBAR_TOKENS": "topbar-tokens",
    "PROMPTIFY_THEME_TOOLBAR": "toolbar",
    "PROMPTIFY_THEME_TOOLBAR_RIGHT": "toolbar-right",
    "PROMPTIFY_THEME_COMPLETION_MENU": "completion-menu",
    "PROMPTIFY_THEME_COMPLETION_MENU_CURRENT": "completion-menu.completion.current",
    "PROMPTIFY_THEME_EDITOR_FRAME_BORDER": "editor-frame.border",
    "PROMPTIFY_THEME_SEARCH_BAR": "search-bar",
    "PROMPTIFY_THEME_SEARCH_LABEL": "search-label",
    "PROMPTIFY_THEME_SEARCH_INPUT": "search-input",
    "PROMPTIFY_THEME_SEARCH_STATUS": "search-status",
    "PROMPTIFY_THEME_SEARCH_MATCH": "search-match",
    "PROMPTIFY_THEME_SEARCH_MATCH_ACTIVE": "search-match-active",
    "PROMPTIFY_THEME_CURRENT_LINE": "current-line",
    "PROMPTIFY_THEME_ERROR_FRAME": "err-frame",
    "PROMPTIFY_THEME_ERROR_FRAME_BORDER": "err-frame.border",
    "PROMPTIFY_THEME_ERROR_FRAME_LABEL": "err-frame.label",
    "PROMPTIFY_THEME_ERROR_TEXT": "err-text",
    "PROMPTIFY_THEME_MENTION_TAG": "mention-tag",
    "PROMPTIFY_THEME_MENTION_PATH": "mention-path",
    "PROMPTIFY_THEME_MENTION_RANGE": "mention-range",
    "PROMPTIFY_THEME_MENTION_DEPTH": "mention-depth",
    "PROMPTIFY_THEME_MENTION_EXT": "mention-ext",
    "PROMPTIFY_THEME_MENTION_GIT_CMD": "mention-git-cmd",
    "PROMPTIFY_THEME_MENTION_CLASS": "mention-class",
    "PROMPTIFY_THEME_MENTION_FUNCTION": "mention-function",
    "PROMPTIFY_THEME_MENTION_METHOD": "mention-method",
    "PROMPTIFY_THEME_INVALID_SYNTAX": "invalid-syntax",
    "PROMPTIFY_THEME_UNRESOLVED_REFERENCE": "unresolved-reference",
    "PROMPTIFY_THEME_HELP_HEADER": "help-header",
    "PROMPTIFY_THEME_HELP_KEY": "help-key",
    "PROMPTIFY_THEME_TRAILING_WHITESPACE": "trailing-whitespace",
    "PROMPTIFY_THEME_EOF_NEWLINE": "eof-newline",
}


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    max_file_size: int
    max_concurrent_reads: int
    locale: str
    default_ignores: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AppBehaviorSettings:
    copy_output_to_clipboard: bool
    save_raw_output: bool


@dataclass(frozen=True, slots=True)
class LoggerSettings:
    verbosity: int
    include_timestamp: bool
    normal_prefix: str
    normal_color: str
    err_prefix: str
    err_color: str
    success_prefix: str
    success_color: str
    warn_prefix: str
    warn_color: str
    info_prefix: str
    info_color: str
    notice_prefix: str
    notice_color: str
    verbose_prefix: str
    verbose_color: str
    input_prefix: str
    input_prefix_color: str
    input_suffix: str


@dataclass(frozen=True, slots=True)
class RenderSettings:
    terminal_fallback_width: int
    terminal_fallback_height: int
    column_padding: int


@dataclass(frozen=True, slots=True)
class TerminalSettings:
    profile: str


@dataclass(frozen=True, slots=True)
class EditorLayoutSettings:
    full_screen: bool
    mouse_support: bool
    ttimeoutlen: float
    completion_menu_max_height: int
    completion_menu_scroll_offset: int
    help_width_min: int
    help_width_max: int
    help_height_min: int
    help_height_max: int
    err_width_min: int
    err_width_max: int
    err_height_min: int
    err_height_max: int


@dataclass(frozen=True, slots=True)
class EditorBehaviorSettings:
    bulk_edit_suspend_seconds: float
    bulk_edit_size_threshold: int
    search_history_limit: int
    token_update_interval: float
    show_help_on_start: bool


@dataclass(frozen=True, slots=True)
class MatchingSettings:
    display_meta_tail_segments: int
    completion_fuzzy_score_cutoff: int
    query_length_switch: int
    path_threshold_short: int
    path_threshold_long: int
    leaf_threshold_short: int
    leaf_threshold_long: int


@dataclass(frozen=True, slots=True)
class IndexerSettings:
    watch_mode: str


@dataclass(frozen=True, slots=True)
class ResolverSettings:
    git_estimate_cache_ttl: float


@dataclass(frozen=True, slots=True)
class ThemeSettings:
    styles: dict[str, str]


@dataclass(frozen=True, slots=True)
class AppSettings:
    runtime: RuntimeSettings
    app_behavior: AppBehaviorSettings
    logger: LoggerSettings
    render: RenderSettings
    terminal: TerminalSettings
    editor_layout: EditorLayoutSettings
    editor_behavior: EditorBehaviorSettings
    matching: MatchingSettings
    indexer: IndexerSettings
    resolver: ResolverSettings
    theme: ThemeSettings


def _get_env(
    env: Mapping[str, str | None],
    key: str,
) -> str | None:
    raw = env.get(key)
    if raw is None:
        return None
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def _parse_int(
    env: Mapping[str, str | None],
    key: str,
    default: int,
    warns: list[str],
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = _get_env(env, key)
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except ValueError:
        warns.append(f"{key} must be an integer, using {default}")
        return default

    if minimum is not None and parsed < minimum:
        warns.append(f"{key} must be >= {minimum}, using {default}")
        return default
    if maximum is not None and parsed > maximum:
        warns.append(f"{key} must be <= {maximum}, using {default}")
        return default
    return parsed


def _parse_float(
    env: Mapping[str, str | None],
    key: str,
    default: float,
    warns: list[str],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = _get_env(env, key)
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except ValueError:
        warns.append(f"{key} must be a number, using {default}")
        return default

    if minimum is not None and parsed < minimum:
        warns.append(f"{key} must be >= {minimum}, using {default}")
        return default
    if maximum is not None and parsed > maximum:
        warns.append(f"{key} must be <= {maximum}, using {default}")
        return default
    return parsed


def _parse_bool(
    env: Mapping[str, str | None],
    key: str,
    default: bool,
    warns: list[str],
) -> bool:
    value = _get_env(env, key)
    if value in (None, ""):
        return default
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    warns.append(f"{key} must be a boolean, using {default}")
    return default


def _parse_choice(
    env: Mapping[str, str | None],
    key: str,
    default: str,
    warns: list[str],
    *,
    choices: frozenset[str],
) -> str:
    value = _get_env(env, key)
    if value in (None, ""):
        return default
    if value in choices:
        return value
    warns.append(f"{key} must be one of {', '.join(sorted(choices))}, using {default}")
    return default


def _parse_string(
    env: Mapping[str, str | None],
    key: str,
    default: str,
    warns: list[str],
) -> str:
    value = _get_env(env, key)
    if value is None:
        return default
    if value == "":
        warns.append(f"{key} cannot be empty, using {default}")
        return default
    return value


def _parse_csv(
    env: Mapping[str, str | None],
    key: str,
    default: tuple[str, ...],
    warns: list[str],
) -> tuple[str, ...]:
    value = _get_env(env, key)
    if value is None:
        return default
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        warns.append(f"{key} must contain at least one value, using defaults")
        return default
    return items


def _build_theme_styles(
    env: Mapping[str, str | None],
    warns: list[str],
) -> dict[str, str]:
    styles = dict(_DEFAULT_THEME_STYLES)
    for env_key, style_key in _THEME_ENV_MAP.items():
        value = _get_env(env, env_key)
        if value is None:
            continue
        if value == "":
            warns.append(f"{env_key} cannot be empty, using theme default")
            continue
        styles[style_key] = value
    return styles


def build_settings(
    env: Mapping[str, str | None] | None = None,
) -> tuple[AppSettings, list[str]]:
    """Build typed settings from an environment mapping"""
    source_env = os.environ if env is None else env
    warns: list[str] = []

    settings = AppSettings(
        runtime=RuntimeSettings(
            max_file_size=_parse_int(
                source_env,
                "PROMPTIFY_MAX_FILE_SIZE",
                5 * 1024 * 1024,
                warns,
                minimum=1,
            ),
            max_concurrent_reads=_parse_int(
                source_env,
                "PROMPTIFY_MAX_CONCURRENT_READS",
                64,
                warns,
                minimum=1,
            ),
            locale=_parse_string(source_env, "PROMPTIFY_LOCALE", "en", warns),
            default_ignores=_parse_csv(
                source_env,
                "PROMPTIFY_DEFAULT_IGNORES",
                (".git/", ".svn/", "__pycache__/", ".venv/", "node_modules/"),
                warns,
            ),
        ),
        app_behavior=AppBehaviorSettings(
            copy_output_to_clipboard=_parse_bool(
                source_env,
                "PROMPTIFY_COPY_OUTPUT_TO_CLIPBOARD",
                True,
                warns,
            ),
            save_raw_output=_parse_bool(
                source_env,
                "PROMPTIFY_SAVE_RAW_OUTPUT",
                True,
                warns,
            ),
        ),
        logger=LoggerSettings(
            verbosity=_parse_int(
                source_env, "PROMPTIFY_LOG_VERBOSITY", 1, warns, minimum=0
            ),
            include_timestamp=_parse_bool(
                source_env, "PROMPTIFY_LOG_TIMESTAMPS", False, warns
            ),
            normal_prefix=_parse_string(
                source_env, "PROMPTIFY_LOG_PREFIX_NORMAL", "[>]", warns
            ),
            normal_color=_parse_choice(
                source_env,
                "PROMPTIFY_LOG_COLOR_NORMAL",
                "ansiblue",
                warns,
                choices=_LOG_COLOR_CHOICES,
            ),
            err_prefix=_parse_string(
                source_env, "PROMPTIFY_LOG_PREFIX_ERROR", "[e]", warns
            ),
            err_color=_parse_choice(
                source_env,
                "PROMPTIFY_LOG_COLOR_ERROR",
                "ansired",
                warns,
                choices=_LOG_COLOR_CHOICES,
            ),
            success_prefix=_parse_string(
                source_env, "PROMPTIFY_LOG_PREFIX_SUCCESS", "[+]", warns
            ),
            success_color=_parse_choice(
                source_env,
                "PROMPTIFY_LOG_COLOR_SUCCESS",
                "ansigreen",
                warns,
                choices=_LOG_COLOR_CHOICES,
            ),
            warn_prefix=_parse_string(
                source_env, "PROMPTIFY_LOG_PREFIX_WARNING", "[w]", warns
            ),
            warn_color=_parse_choice(
                source_env,
                "PROMPTIFY_LOG_COLOR_WARNING",
                "ansiyellow",
                warns,
                choices=_LOG_COLOR_CHOICES,
            ),
            info_prefix=_parse_string(
                source_env, "PROMPTIFY_LOG_PREFIX_INFO", "[i]", warns
            ),
            info_color=_parse_choice(
                source_env,
                "PROMPTIFY_LOG_COLOR_INFO",
                "ansiblue",
                warns,
                choices=_LOG_COLOR_CHOICES,
            ),
            notice_prefix=_parse_string(
                source_env, "PROMPTIFY_LOG_PREFIX_NOTICE", "[*]", warns
            ),
            notice_color=_parse_choice(
                source_env,
                "PROMPTIFY_LOG_COLOR_NOTICE",
                "ansimagenta",
                warns,
                choices=_LOG_COLOR_CHOICES,
            ),
            verbose_prefix=_parse_string(
                source_env, "PROMPTIFY_LOG_PREFIX_VERBOSE", "[v]", warns
            ),
            verbose_color=_parse_choice(
                source_env,
                "PROMPTIFY_LOG_COLOR_VERBOSE",
                "ansigray",
                warns,
                choices=_LOG_COLOR_CHOICES,
            ),
            input_prefix=_parse_string(
                source_env, "PROMPTIFY_LOG_INPUT_PREFIX", "[<]", warns
            ),
            input_prefix_color=_parse_choice(
                source_env,
                "PROMPTIFY_LOG_INPUT_PREFIX_COLOR",
                "ansicyan",
                warns,
                choices=_LOG_COLOR_CHOICES,
            ),
            input_suffix=_parse_string(
                source_env, "PROMPTIFY_LOG_INPUT_SUFFIX", ">>", warns
            ),
        ),
        render=RenderSettings(
            terminal_fallback_width=_parse_int(
                source_env,
                "PROMPTIFY_UI_TERM_FALLBACK_WIDTH",
                80,
                warns,
                minimum=20,
            ),
            terminal_fallback_height=_parse_int(
                source_env,
                "PROMPTIFY_UI_TERM_FALLBACK_HEIGHT",
                20,
                warns,
                minimum=5,
            ),
            column_padding=_parse_int(
                source_env,
                "PROMPTIFY_UI_COLUMN_PADDING",
                4,
                warns,
                minimum=0,
            ),
        ),
        terminal=TerminalSettings(
            profile=_parse_choice(
                source_env,
                "PROMPTIFY_TERMINAL_PROFILE",
                "auto",
                warns,
                choices=frozenset(
                    {
                        "auto",
                        "modern",
                        "legacy-cmd",
                        "vscode",
                        "windows-terminal",
                        "conhost",
                    }
                ),
            )
        ),
        editor_layout=EditorLayoutSettings(
            full_screen=_parse_bool(
                source_env, "PROMPTIFY_UI_FULL_SCREEN", True, warns
            ),
            mouse_support=_parse_bool(
                source_env, "PROMPTIFY_UI_MOUSE_SUPPORT", True, warns
            ),
            ttimeoutlen=_parse_float(
                source_env,
                "PROMPTIFY_UI_TTIMEOUTLEN",
                0.05,
                warns,
                minimum=0.0,
            ),
            completion_menu_max_height=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_COMPLETION_MENU_MAX_HEIGHT",
                12,
                warns,
                minimum=1,
            ),
            completion_menu_scroll_offset=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_COMPLETION_MENU_SCROLL_OFFSET",
                1,
                warns,
                minimum=0,
            ),
            help_width_min=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_HELP_WIDTH_MIN",
                40,
                warns,
                minimum=1,
            ),
            help_width_max=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_HELP_WIDTH_MAX",
                160,
                warns,
                minimum=1,
            ),
            help_height_min=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_HELP_HEIGHT_MIN",
                12,
                warns,
                minimum=1,
            ),
            help_height_max=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_HELP_HEIGHT_MAX",
                40,
                warns,
                minimum=1,
            ),
            err_width_min=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_ERROR_WIDTH_MIN",
                28,
                warns,
                minimum=1,
            ),
            err_width_max=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_ERROR_WIDTH_MAX",
                96,
                warns,
                minimum=1,
            ),
            err_height_min=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_ERROR_HEIGHT_MIN",
                6,
                warns,
                minimum=1,
            ),
            err_height_max=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_ERROR_HEIGHT_MAX",
                20,
                warns,
                minimum=1,
            ),
        ),
        editor_behavior=EditorBehaviorSettings(
            bulk_edit_suspend_seconds=_parse_float(
                source_env,
                "PROMPTIFY_EDITOR_BULK_EDIT_SUSPEND_SECONDS",
                0.35,
                warns,
                minimum=0.0,
            ),
            bulk_edit_size_threshold=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_BULK_EDIT_SIZE_THRESHOLD",
                2048,
                warns,
                minimum=1,
            ),
            search_history_limit=_parse_int(
                source_env,
                "PROMPTIFY_EDITOR_SEARCH_HISTORY_LIMIT",
                8,
                warns,
                minimum=1,
            ),
            token_update_interval=_parse_float(
                source_env,
                "PROMPTIFY_EDITOR_TOKEN_UPDATE_INTERVAL",
                0.5,
                warns,
                minimum=0.05,
            ),
            show_help_on_start=_parse_bool(
                source_env,
                "PROMPTIFY_EDITOR_SHOW_HELP_ON_START",
                False,
                warns,
            ),
        ),
        matching=MatchingSettings(
            display_meta_tail_segments=_parse_int(
                source_env,
                "PROMPTIFY_MATCH_DISPLAY_META_TAIL_SEGMENTS",
                3,
                warns,
                minimum=1,
            ),
            completion_fuzzy_score_cutoff=_parse_int(
                source_env,
                "PROMPTIFY_COMPLETION_FUZZY_SCORE_CUTOFF",
                40,
                warns,
                minimum=0,
                maximum=100,
            ),
            query_length_switch=_parse_int(
                source_env,
                "PROMPTIFY_MATCH_QUERY_LENGTH_SWITCH",
                6,
                warns,
                minimum=1,
            ),
            path_threshold_short=_parse_int(
                source_env,
                "PROMPTIFY_MATCH_PATH_THRESHOLD_SHORT",
                78,
                warns,
                minimum=0,
                maximum=100,
            ),
            path_threshold_long=_parse_int(
                source_env,
                "PROMPTIFY_MATCH_PATH_THRESHOLD_LONG",
                86,
                warns,
                minimum=0,
                maximum=100,
            ),
            leaf_threshold_short=_parse_int(
                source_env,
                "PROMPTIFY_MATCH_LEAF_THRESHOLD_SHORT",
                84,
                warns,
                minimum=0,
                maximum=100,
            ),
            leaf_threshold_long=_parse_int(
                source_env,
                "PROMPTIFY_MATCH_LEAF_THRESHOLD_LONG",
                90,
                warns,
                minimum=0,
                maximum=100,
            ),
        ),
        indexer=IndexerSettings(
            watch_mode=_parse_choice(
                source_env,
                "PROMPTIFY_INDEX_WATCH_MODE",
                "auto",
                warns,
                choices=frozenset({"auto", "native", "polling", "off"}),
            )
        ),
        resolver=ResolverSettings(
            git_estimate_cache_ttl=_parse_float(
                source_env,
                "PROMPTIFY_GIT_ESTIMATE_CACHE_TTL",
                5.0,
                warns,
                minimum=0.0,
            )
        ),
        theme=ThemeSettings(styles=_build_theme_styles(source_env, warns)),
    )

    if settings.editor_layout.help_width_min > settings.editor_layout.help_width_max:
        warns.append(
            "PROMPTIFY_EDITOR_HELP_WIDTH_MIN cannot exceed PROMPTIFY_EDITOR_HELP_WIDTH_MAX, using defaults"
        )
        settings = _replace_editor_layout(
            settings,
            help_width_min=40,
            help_width_max=160,
        )

    if settings.editor_layout.help_height_min > settings.editor_layout.help_height_max:
        warns.append(
            "PROMPTIFY_EDITOR_HELP_HEIGHT_MIN cannot exceed PROMPTIFY_EDITOR_HELP_HEIGHT_MAX, using defaults"
        )
        settings = _replace_editor_layout(
            settings,
            help_height_min=12,
            help_height_max=40,
        )

    if settings.editor_layout.err_width_min > settings.editor_layout.err_width_max:
        warns.append(
            "PROMPTIFY_EDITOR_ERROR_WIDTH_MIN cannot exceed PROMPTIFY_EDITOR_ERROR_WIDTH_MAX, using defaults"
        )
        settings = _replace_editor_layout(
            settings,
            err_width_min=28,
            err_width_max=96,
        )

    if settings.editor_layout.err_height_min > settings.editor_layout.err_height_max:
        warns.append(
            "PROMPTIFY_EDITOR_ERROR_HEIGHT_MIN cannot exceed PROMPTIFY_EDITOR_ERROR_HEIGHT_MAX, using defaults"
        )
        settings = _replace_editor_layout(
            settings,
            err_height_min=6,
            err_height_max=20,
        )

    return settings, warns


def _replace_editor_layout(
    settings: AppSettings,
    **overrides: int | bool | float,
) -> AppSettings:
    layout = settings.editor_layout
    updated_layout = EditorLayoutSettings(
        full_screen=layout.full_screen,
        mouse_support=layout.mouse_support,
        ttimeoutlen=layout.ttimeoutlen,
        completion_menu_max_height=layout.completion_menu_max_height,
        completion_menu_scroll_offset=layout.completion_menu_scroll_offset,
        help_width_min=int(overrides.get("help_width_min", layout.help_width_min)),
        help_width_max=int(overrides.get("help_width_max", layout.help_width_max)),
        help_height_min=int(overrides.get("help_height_min", layout.help_height_min)),
        help_height_max=int(overrides.get("help_height_max", layout.help_height_max)),
        err_width_min=int(overrides.get("err_width_min", layout.err_width_min)),
        err_width_max=int(overrides.get("err_width_max", layout.err_width_max)),
        err_height_min=int(overrides.get("err_height_min", layout.err_height_min)),
        err_height_max=int(overrides.get("err_height_max", layout.err_height_max)),
    )
    return AppSettings(
        runtime=settings.runtime,
        app_behavior=settings.app_behavior,
        logger=settings.logger,
        render=settings.render,
        terminal=settings.terminal,
        editor_layout=updated_layout,
        editor_behavior=settings.editor_behavior,
        matching=settings.matching,
        indexer=settings.indexer,
        resolver=settings.resolver,
        theme=settings.theme,
    )


APP_SETTINGS, SETTINGS_WARNINGS = build_settings()

MAX_FILE_SIZE = APP_SETTINGS.runtime.max_file_size
MAX_CONCURRENT_READS = APP_SETTINGS.runtime.max_concurrent_reads
LOCALE = APP_SETTINGS.runtime.locale


def consume_settings_warns() -> list[str]:
    """Return current settings warnings and clear them for one-time logging"""
    warns = list(SETTINGS_WARNINGS)
    SETTINGS_WARNINGS.clear()
    return warns

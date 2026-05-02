# README

`promptify` is an asynchronous CLI tool for building context-rich prompts from a local project. it lets you attach files, directories, trees, symbols, and `git` state directly inside a prompt through a compact mention syntax.

## WHAT

`promptify` uses a case-based workflow. each case defines its own prompt templates, file filters, and ignore rules, so you can reuse a workflow without repeatedly rebuilding context by hand.

## FEATURES

### GENERAL

- built on `asyncio` with structured concurrency via `TaskGroup` and `aiofiles`;
- keeps an in-memory project index for fast matching and autocomplete;
- uses `watchdog` for live updates, with configurable native, polling, or disabled watch modes;
- strictly validates paths so reads stay inside the chosen project root;
- supports file slices, directory trees, extension filters, symbol extraction, and `git` status / diff / log / history mentions, including optional branch selectors;
- stores user-facing copy through `strings/en.json`, with optional locale resource files for large multiline text;
- exposes runtime behavior, editor tuning, logger formatting, and theme styles through `.env`;
- detects terminal capabilities and adapts rendering for legacy `cmd.exe` and classic Windows console hosts.

### MODES

#### SIMPLE

also called legacy mode. `promptify` reads `legacy.md` from the selected case and resolves mentions in one pass.

#### INTERACTIVE

a terminal editor powered by `prompt-toolkit`.

- fuzzy completion for files, directories, trees, extensions, symbols, and `git` mentions;
- VS Code-style search and replace widget with match counts, wrap reporting, search history, and search-mode toggles for case, whole-word, regex, and preserve-case replace;
- jump-to-line input with `:line[:character]` and `:line,character` targets;
- issue overlays for malformed mentions and unresolved references before save;
- syntax highlighting, trailing whitespace marking, EOF newline indicators, active-line highlighting, and optional line numbers;
- configurable layout, behavior, colors, and terminal compatibility through `.env`.

##### CONTROLS

the in-app help screen is authoritative, but the main defaults are...

- `Ctrl+G` / `F1`: help
- `Ctrl+F`: search
- `Ctrl+R`: toggle replace
- `Alt+G`: jump to `:line[:character]` or `:line,character`
- `Alt+Z`: toggle word wrap
- `Ctrl+S`: resolve and save
- `Ctrl+Q` / `F10`: abort with confirmation
- `F6` / `F7` / `F8`: toggle match case, whole word, and regex while search is open
- `Ctrl+F6`: toggle preserve-case replace while replace is open
- `Up` / `Down`: search history while the search field is focused
- `Enter` / `Shift+Enter`: next and previous search result while the search field is focused
- `Enter` / `Ctrl+Alt+Enter`: replace current result or replace all while the replace field is focused
- `Enter` / `Ctrl+N`: next issue while issue mode is open
- `Ctrl+R` / `Ctrl+P`: previous issue while issue mode is open

##### MENTIONS

| call                  | description                           | example                         |
| :-------------------- | :------------------------------------ | :------------------------------ |
| `<@file:path>`        | attach a file                         | `<@file:src/main.py>`           |
| `<@file:path:range>`  | attach a sliced file                  | `<@file:src/main.py:first 32>`  |
| `<@dir:path>`         | attach files under a directory        | `<@dir:src>`                    |
| `<@tree:path>`        | attach a directory tree               | `<@tree:src>`                   |
| `<@tree:path:level>`  | attach a depth-limited directory tree | `<@tree:src:2>`                 |
| `<@ext:list>`         | attach files by extension             | `<@ext:toml,py>`                |
| `<@symbol:path:name>` | attach a class, method, or function   | `<@symbol:src/main.py:App.run>` |
| `<@git:diff>`         | attach working tree diff              | `<@git:diff>`                   |
| `<@git:diff:path>`    | attach diff for a file or directory   | `<@git:diff:src/main.py>`       |
| `<@git:log>`          | attach recent `git log` output        | `<@git:log>`                    |
| `<@git:log:n>`        | attach the latest `n` commits         | `<@git:log:2>`                  |
| `<@git:history>`      | attach recent commits with patches    | `<@git:history>`                |
| `<@git:history:n>`    | attach the latest `n` commit diffs    | `<@git:history:2>`              |
| `<@git:status>`       | attach working tree status            | `<@git:status>`                 |
| `<@git:[branch]:...>` | run a git mention against a branch    | `<@git:[master]:log:2>`         |
| `[@project]`          | attach the project tree               | `[@project]`                    |

`<@git:log>` defaults to the latest `20` commits when no count is given. `<@git:history>` defaults to `5` commits because it includes full patches and grows much faster.

supported file ranges...

- `first n`
- `last n`
- `n-m`
- `#n`

## CASES

cases live under `cases/`.

```log
cases/
└── my_case/
    ├── config.json
    ├── .caseignore
    ├── system.md
    ├── prompt.md
    └── legacy.md
```

example `config.json`...

```json
{
    "name": "my_case",
    "types": [
        ".py",
        ".md",
        "README.md",
        ".github/workflows/*.yml"
    ],
    "ignores": ".caseignore",
    "system": "system.md",
    "prompt": "prompt.md",
    "legacy": "legacy.md"
}
```

## CONFIGURATION

local preferences are loaded from `.env`. these settings are not treated as secrets in this repository.

the full documented surface is in [.env.example](/C:/Users/lucky/Documents/vscode/python/tools/dirs/ai/promptify/.env.example:1), including...

- runtime limits like max file size and concurrent reads;
- output behavior such as clipboard copy and raw prompt saving;
- logger prefixes, colors, verbosity, and timestamps;
- terminal and menu rendering fallbacks, including `PROMPTIFY_TERMINAL_PROFILE` for legacy `cmd.exe`, classic `conhost`, raster-font consoles, or forced modern profiles;
- watch mode selection;
- advanced real-token counting toggle with automatic fallback to the legacy heuristic estimator;
- exact tokenizer data stored under `data/o200k_base.tiktoken`, with automatic download if it is missing and safe fallback when the download is unavailable;
- matching thresholds and completion tuning;
- editor layout, line-number gutter, search history, bulk-paste tuning, and token refresh timing;
- editor layout, line-number gutter, word wrap, search history, bulk-paste tuning, and token refresh timing;
- full prompt-toolkit style overrides for the interactive theme.

invalid values fall back safely to code defaults through [settings.py](/C:/Users/lucky/Documents/vscode/python/tools/dirs/ai/promptify/src/promptify/core/settings.py:1).

when `PROMPTIFY_TERMINAL_PROFILE=auto`, `promptify` detects common environments such as VS Code, Windows Terminal, and legacy `cmd.exe`. older `cmd.exe` sessions automatically switch to ASCII-safe borders, tree connectors, and EOF markers so UI chrome remains readable even without box-drawing glyph support. if you need the old classic Windows console compatibility profile, set `PROMPTIFY_TERMINAL_PROFILE=conhost` explicitly to keep prompt-toolkit full-screen mode off and mouse support disabled.

## TESTING

the project is unit-test driven and expects source changes to stay covered.

- use `get_string(...)` in tests when asserting localized UI text;
- keep tests sandboxed and deterministic;
- tests seed `PROMPTIFY_*` values from `.env.example` through `tests/_settings_master.py`, so repo-local `.env` changes do not shift test expectations;
- settings-sensitive tests reuse the generated multi-pass matrix from `tests/_settings_master.py`; set `PROMPTIFY_TEST_PASS_COUNT` to change the pass count, which defaults to `4`;
- preserve Pylance basic type-checking cleanliness.

run tests...

```bash
uv run pytest -v
```

or on Windows...

```powershell
./scripts/llt.bat
```

format and lint...

```bash
uv run ruff check --fix
uv run ruff format
```

or on Windows...

```powershell
./scripts/llf.bat
```

## INSTALL

1. install [uv](https://github.com/astral-sh/uv)
2. sync the environment

```bash
uv sync
```

run...

```bash
uv run promptify
```

or...

```powershell
./scripts/llr.bat
```

module entry point...

```bash
uv run python -m promptify
```

## GUARDS

- default max file size is `5242880` bytes (`5 MiB`), configurable through `.env`;
- default max concurrent reads is `64`, configurable through `.env`;
- invalid env values never fail startup and instead fall back with warnings;
- legacy terminal profiles avoid unsupported box-drawing glyphs, disable mouse support automatically where needed, and keep full-screen mode off when the explicit `conhost` profile is selected;
- recursive system resolution detects loops and neutralizes them;
- clipboard failures do not abort prompt generation;
- missing `git` or missing `.git` repositories are handled gracefully.

## CONTRIBUTING

automation and CLI agents should also follow [AGENTS.md](/C:/Users/lucky/Documents/vscode/python/tools/dirs/ai/promptify/AGENTS.md:1).

repo maintenance helpers live under [`scripts/`](C:/Users/lucky/Documents/vscode/python/tools/dirs/ai/promptify/scripts/). [`filter.ps1`](/C:/Users/lucky/Documents/vscode/python/tools/dirs/ai/promptify/scripts/filter.ps1:1) prompts for the source and target git identity, refuses no-op rewrites, rewrites git author history using `git-filter-repo`, restores `origin`, force-pushes rewritten refs, and removes the generated `.mailmap-rewrite` file after the run.

## DEMO

![a demo video showcasing `promptify`](docs/vid/demo.gif)

### MENU

![a screenshot displaying welcome screen with list of use cases available to use](docs/img/0.png)

![a screenshot depicting list of available working modes - simple and interactive](docs/img/1.png)

### EDITOR

![`promptify` interactive editor](docs/img/3.png)

![toolbar showing controls information](docs/img/10.png)

![a user selecting file mention in the prompt - by mentioning, user can insert contents of a file into the prompt in a convenient way](docs/img/4.png)

![a user typing `README` to quickly select `README.md` from the suggestions list](docs/img/5.png)

![another demonstration of fuzzy matching using `main.py` to attach `/src/promptify/main.py`](docs/img/6.png)

![the result of `main.py` fuzzy matching](docs/img/7.png)

![user mentioning a symbol from `main.py` file. in this example user attaches `App` class](docs/img/8.png)

![a screenshot of a finished prompt in a terminal before saving and resolving mentions](docs/img/9.png)

![a screenshot of a terminal showing complete output of the script](docs/img/11.png)

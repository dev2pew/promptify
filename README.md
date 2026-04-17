# README

`promptify` is an asynchronous CLI tool designed to bridge the gap between your local source code and LLMs. it allows you to "attach" project context-specific files, entire directories, file types, directory trees, and even specific symbols or `git` `diff`s directly into your prompts using a clean, mention-based syntax.

## WHAT

`promptify` uses a "case" based system. each "case" represents a specific workflow with its own prompt templates and exclusion rules using `.caseignore`. it allows you to build massive, context-rich prompts without the manual copy-paste headache.

## FEATURES

### GENERAL

- built on `asyncio` with structured concurrency using `TaskGroup` and `aiofiles` for fully non-blocking, high-performance file I/O and mention resolution;
- uses `watchdog` to maintain an in-memory map of your project, paired with `rapidfuzz` for ultra-fast, near-instant fuzzy autocomplete even in massive codebases;
- strict path validation ensures the tool never reads files outside of your specified project directory;
- automatically detects language extensions to wrap code in appropriate markdown fences (e.g., `python`);
- advanced AST-like symbol extraction powered by `pygments` to target specific classes and methods;
- native `git` integration for pulling working tree status and diffs.

### MODES

#### SIMPLE

also known as legacy mode. perfect for static, repeatable workflows. it reads a `legacy.md` template from your `case` directory and resolves all mentions in a single pass. an example use case is to generate a standard "code review" report for a specific project.

#### INTERACTIVE

a rich terminal-based text editor for crafting complex, one-off prompts.

- type `<@` to trigger a fuzzy-search menu for files, folders, extensions, symbols, and `git` commands;
- resolves mentions exactly once. this prevents "prompt leaks". if your source code contains `<@file:...>` strings, `promptify` treats them as static text rather than trying to resolve them recursively;
- features real-time syntax highlighting, trailing whitespace detection, EOF newline indicators, and matching bracket highlighting.

##### CONTROLS

the editor is powered by `prompt-toolkit` and supports standard IDE shortcuts...

---

| controls | do | icon |
| :-- | :-- | :--: |
| `^[G]` / `[F1]` | help | 📖 |
| `^[F]` | find | 👁️‍🗨️ |
| `^[S]` | resolve | 💾 |
| `^[Q]` | abort | 🚫 |

---

| editing | do | icon |
| :-- | :-- | :--: |
| `^[A]` | select all | 🔲 |
| `[Shift]` | select | 🔳 |
| `^[Z/Y]` | undo / redo | ⬅️ / 🔄 |
| `^[C/X/V]` | copy / cut / paste | 📋 / ✂️ / 📥 |
| `[Tab]` | indent / autocomplete | ⏩ / 🆗 |
| `[Shift]` + `[Tab]` | unindent | ⏪ |
| `[Alt]` + `[^/v]` | shift cursor | ⬆️ / ⬇️ |
| `^[/]` | comment out | 💬 |
| `^[W/Del]` | delete previous / next | ❌ / ✖️ |
| `[Enter]` | newline / accept | ↩️ |

---

| navigation | do | icon |
| :-- | :-- | :--: |
| `[^/v/</>]` | move | 🧭 |
| `^[^/v/</>]` | next / previous | 👆 |
| `[Home/End]` | start / end | 🚩 / 🏴 |
| `^[Home/End]` | file start / end | 📄👆 |
| `[PgUp/PgDn]` | up / down (15x) | 🔺 / 🔻 |

---

##### MENTIONS

---

| call | desc. | ex. | icon |
| :-- | :-- | :-- | :--: |
| `<@file:path>` | attach file | `<@file:src/main.py>` | 📄 |
| `<@file:path:range>` | attach sliced file<br><br>`first [n]`<br>`last [n]`<br>`[n]-[m]`<br>`#[n]` | `<@file:src/main.py:first 32>`<br>`<@file:src/main.py:last 16>`<br>`<@file:src/main.py:32-64>`<br>`<@file:src/main.py:#128>` | 📄↕️ |
| `<@dir:path>` | attach folder | `<@dir:src>` | 📁 |
| `<@tree:path>` | attach folder structure | `<@tree:src>` | 📁 |
| `<@ext:list>` | attach files by extension | `<@ext:toml,py>` | 📄🔍 |
| `<@symbol:path:name>` | attach class, method, function *(AST)* | `<@symbol:src/main.py:Class.method>` | 📄©️ |
| `<@git:diff>` | attach working tree `diff` | `<@git:diff>` | 🔄⚖️ |
| `<@git:diff:path>` | attach working tree `diff` for target | `<@git:diff:src/main.py>`<br>`<@git:diff:src>` | 📄 / 📁 + ⚖️ |
| `<@git:status>` | attach working tree `status` | `<@git:status>` | 🔄❔ |
| `[@project]` | insert project structure | `[@project]` | 🧱 |

---

### CASES

define your workflows in the `cases/` directory...

```log
cases/
└── my_case/
    ├── config.json    # case configuration
    ├── .caseignore    # ignore rules
    ├── prompt.md      # interactive mode template
    └── legacy.md      # simple AKA legacy mode template

```

typical contents of `config.json`...

```json
{
    "name": "my_case",
    "types": [
        ".sample",
        ".file",
        ".extensions",

        ".you",
        ".can",
        ".include",
        ".filenames",

        ".as",
        ".well",

        "README.md",
    ],
    "ignores": ".caseignore",
    "system": "system.md",
    "prompt": "prompt.md",
    "legacy": "legacy.md"
}


```

### TESTING

`promptify` is built with a "test-first" mentality.

- all core logic is verified via `pytest` and `pytest-asyncio`, with graceful CI/CD console fallbacks;
- tests generate a temporary filesystem to verify indexing, line-slicing, and loop prevention without touching your actual data;
- strictly formatted and linted using `ruff` for `python` 3.13+ compatibility.

run tests...

```bash
uv run pytest -v

```

format code...

```bash
uv run ruff format src/ tests/

```

---

### INSTALL

1. get [uv](https://github.com/astral-sh/uv);
2. setup using...

```bash
uv sync

```

1. run using...

```bash
uv run promptify

```

or via the module entry point...

```bash
uv run python -m promptify

```

---

### GUARDS

- prevents reading files larger than `5` MB; (configurable)
- if using `resolve_system`, the engine detects infinite loops (e.g., `A.md` calls `A.md`) and neutralizes them with an HTML warning comment;
- limits concurrent file reads to 100 to prevent OS file descriptor exhaustion;
- gracefully handles missing `git` installations or missing `.git` repositories.

## DEMO

animated walkthrough showcasing interactive editor and basic usage examples...

![a demo video showcasing `promptify`](docs/vid/demo.gif)

### MENU

the app opens to a welcome screen that lists available use cases.

![a screenshot displaying welcome screen with list of use cases available to use](docs/img/0.png)

you can pick a working mode from the menu, either `simple` or `interactive`...

![a screenshot depicting list of available working modes - simple and interactive](docs/img/1.png)

### EDITOR

#### OVERVIEW

the editor is where you compose prompts and attach project files or symbols. it's an interactive, terminal-based editor with helpful UI elements and keyboard shortcuts.

![`promptify` interactive editor](docs/img/3.png)

a toolbar at the bottom shows available shortcuts and controls so you always know how to navigate and use mentions.

![toolbar showing controls information](docs/img/10.png)

#### CALLS

type `<@` to trigger mentions AKA calls in the editor. mentions let you quickly attach files from the project into your prompt, so you can include file contents without leaving the editor.

![a user selecting file mention in the prompt - by mentioning, user can insert contents of a file into the prompt in a convenient way](docs/img/4.png)

#### SUGGESTIONS

the editor offers fuzzy matching, autocompletion, and suggestions (powered by the `prompt-toolkit` library) to speed up selection.

for example, typing `read` brings up `README.md` in the suggestions list.

![a user typing `README` to quickly select `README.md` from the suggestions list](docs/img/5.png)

fuzzy matching also works for file paths - here we use `main.py` to attach `/src/promptify/main.py`.

![another demonstration of fuzzy matching using `main.py` to attach `/src/promptify/main.py`](docs/img/6.png)

...and here's the result after selecting main.py from the suggestions...

![the result of `main.py` fuzzy matching](docs/img/7.png)

#### SYMBOLS

the editor can parse source files, cache symbols, and let you attach specific symbols (classes, functions, etc.) into your prompt. this is useful when you need only a fragment of a file.

![user mentioning a symbol from `main.py` file. in this example user attaches `App` class](docs/img/8.png)

a typical prompt in promptify shows resolved mentions inline before you save or run it.

![a screenshot of a finished prompt in a terminal before saving and resolving mentions](docs/img/9.png)

when you resolve and run the prompt, promptify copies the final prompt to your clipboard and prints the full output in the terminal.

![a screenshot of a terminal showing complete output of the script](docs/img/11.png)

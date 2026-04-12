# README

`promptify` is an asynchronous CLI tool designed to bridge the gap between your local source code and LLMs. It allows you to "attach" project context—specific files, entire directories, file types, or directory trees—directly into your prompts using a clean, mention-based syntax.

## WHAT

`promptify` uses a Case-based system. Each "Case" represents a specific workflow (e.g., "Refactor", "Documentation", "Bug Fix") with its own prompt templates and exclusion rules (`.caseignore`). It allows you to build massive, context-rich prompts without the manual copy-paste headache.

## FEATURES

### GENERAL

- Built on `asyncio` with structured concurrency (`TaskGroup`) and `aiofiles` for fully non-blocking, high-performance file I/O and mention resolution;
- Uses `watchdog` to maintain an in-memory map of your project, paired with `rapidfuzz` for ultra-fast, near-instant fuzzy autocomplete even in massive codebases;
- Strict path validation ensures the tool never reads files outside of your specified project directory;
- Automatically detects language extensions to wrap code in appropriate Markdown fences. (e.g., `python`)

### MODES

#### SIMPLE

Also known as legacy mode. Perfect for static, repeatable workflows. It reads a `legacy.md` template from your Case directory and resolves all mentions in a single pass.

> Use Case
>
> Generating a standard "Code Review" report for a specific file.

#### INTERACTIVE

A rich terminal-based text editor for crafting complex, one-off prompts.

- Type `<@` to trigger a fuzzy-search menu for files, folders, and extensions;
- Resolves mentions exactly once. This prevents "Prompt Leaks"—if your source code contains `<@file:...>` strings, `promptify` treats them as static text rather than trying to resolve them recursively.

##### CONTROLS

The editor is powered by `prompt-toolkit` and supports standard IDE shortcuts...

---

| Hotkey | Action |
| :-- | :-- |
| `[Ctrl]` + `[S]` | Save and generate final prompt |
| `[Ctrl]` + `[G]` or `[F1]` | Toggle the Help overlay |
| `[Ctrl]` + `[/]` | Context-aware commenting (wraps selection in `#` or `//` based on cursor position) |
| `[Tab]` | Trigger/Cycle autocompletions |
| `[Shift]` + `[Arrows]` | Text selection |

---

##### MENTIONS

---

| Tag | Description | Example |
| :-- | :-- | :-- |
| <@file:path> | Attaches a specific file. | <@file:src/main.py> |
| <@file:path:range> | Attaches a specific line slice. | <@file:app.py:10-20> or first 50 |
| <@dir:path> | Attaches all allowed files in a folder. | <@dir:src/utils> |
| <@ext:list> | Attaches files by extension. | "<@ext:py,ts>" |
| [@project] | Generates a TREE /F style directory map. | [@project] |

---

### CASES

Define your workflows in the `cases/` directory...

```log
cases/
└── my-feature/
    ├── config.json   # Define allowed file types
    ├── .caseignore    # Rules like *.log or secret.key
    ├── prompt.md      # Initial text for Interactive Mode
    └── legacy.md      # Template for Simple Mode

```

### TESTING

`promptify` is built with a "Test-First" mentality.

- 100% Green Suite: All core logic is verified via `pytest` and `pytest-asyncio`, with graceful CI/CD console fallbacks;
- Dynamic Sandbox: Tests generate a temporary filesystem to verify indexing, line-slicing, and loop prevention without touching your actual data;
- Linting: Strictly formatted and linted using Ruff for Python 3.13+ compatibility.

Run Tests...

```bash
uv run pytest -v

```

Format Code...

```bash
uv run ruff format src/

```

---

### INSTALL

1. Get [uv](https://github.com/astral-sh/uv);
2. Setup using...

```bash
uv sync

```

1. Run using...

```bash
uv run promptify

```

Or via the module entry point...

```bash
uv run python -m promptify

```

---

### GUARDS

- Prevents reading files larger than 5MB; (configurable)
- If using `resolve_system`, the engine detects infinite loops (e.g., `A.md` calls `A.md`) and neutralizes them with an HTML warning comment;
- Limits concurrent file reads to 100 to prevent OS file descriptor exhaustion.

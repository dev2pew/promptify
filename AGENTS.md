# PROMPTIFY AGENT GUIDE

## SCOPE

- This repository targets modern Python and should stay compatible with the current project baseline in `pyproject.toml`;
- Prefer small, typed, test-backed refactors over broad speculative rewrites.

## CORE RULES

- Keep user-facing copy indexed from `strings/en.json`;
- In source code, always use string lookups with an inline fallback;
- Treat `strings/en.json` as the single source of truth for UI and message text, using resource references in `strings/<locale>/*.res` for large multiline blocks when needed;
- Route new environment configuration through `src/promptify/core/settings.py`;
- Invalid configuration values must never crash import-time startup. Fall back safely;
- Preserve `basedpyright` cleanliness under the repo `scripts/c.(bat|sh)` scripts; treat it as stricter than Pylance basic checking and fix issues rather than silencing them unless there is a clear compatibility reason;
- Prefer shared helpers over repeated logic, especially in editor, resolver, and completion flows;
- Prefer `src/promptify/shared/` for cross-cutting helpers reused across modules, and keep editor keybinding logic decomposed under `src/promptify/ui/keybinding/` instead of growing a single binding file;
- Keep the interactive editor package-backed under `src/promptify/ui/editor/`; route editor-neutral state and pure helpers into `src/promptify/shared/editor_state.py` and `src/promptify/shared/editor_support.py` instead of re-growing a monolithic `editor.py`;
- Reuse existing code and helpers before adding new logic; do not reinvent the wheel;
- Preserve terminal compatibility across modern terminals, classic Windows console hosts, and legacy `cmd.exe`; avoid assuming Unicode box-drawing support or safe full-screen behavior everywhere;
- Treat performance as a correctness concern in editor, resolver, and token-counting code paths; avoid changes that add eager startup work, repeated full-buffer scans, or unnecessary background churn;
- Match the existing codebase style for structure, naming, localization, and user-facing tone when adding or changing code.

## TOKEN COUNTING RULES

- The advanced token counter is editor-facing only. Do not add exact token-count work to CLI, menu, case selection, or other non-editor flows unless explicitly required;
- Resolver construction must stay cheap. Do not eagerly load or parse the tokenizer model during `PromptResolver` or token-counter initialization;
- The exact tokenizer model lives at `data/o200k_base.tiktoken`;
- If the model file is missing, the code may download it on demand; if download fails or the network is unavailable, token counting must fall back safely to the legacy heuristic estimator;
- Token counting must never make startup or import-time network calls;
- Reuse shared caches before adding new token logic. Preserve the existing design where unchanged mention expansions and unchanged token pieces can be reused across edits;
- When editing the token path, prefer incremental or chunk-aware reuse over re-tokenizing the entire rendered prompt after every small text change;
- Background token work must stop when the interactive editor exits. Do not leave token-count tasks running after save, quit, or return to non-editor screens;
- Changes in this area must be careful about cancellation, offline behavior, and large-project responsiveness.

## TESTING RULES

- Test using `$env:UV_CACHE_DIR='C:\Users\lucky\Documents\vscode\python\tools\dirs\ai\promptify\.uv-cache'; ./scripts/t.bat` to avoid requiring elevation;
- Add or update unit tests for every behavioral change;
- Run the repo type-check wrapper before finishing work using `$env:UV_CACHE_DIR='C:\Users\lucky\Documents\vscode\python\tools\dirs\ai\promptify\.uv-cache'; ./scripts/c.bat`;
- `scripts/c.(bat|sh)` now refresh the repo-root `problems.json` file with a compact grouped `basedpyright` report on each run, print grouped issue-to-file output across all collected diagnostics for inspection, and treat `summary.errorCount` as the wrapper pass/fail gate; use that generated artifact for diagnostics instead of committing a stale snapshot;
- Tests should assert localized text through `get_string(...)` instead of hardcoded copies when the value comes from `strings/en.json`;
- Keep tests deterministic and sandboxed;
- The test harness seeds `PROMPTIFY_*` values from `.env.example` through `tests/_settings_master.py` before importing application modules, so local `.env` tweaks must not influence test expectations;
- Settings-sensitive tests should reuse the generated passes from `tests/_settings_master.py` instead of hardcoding layout or render defaults; set `PROMPTIFY_TEST_PASS_COUNT` to control the number of generated passes, with a default of `4`;
- Prefer repo-local test artifacts over OS temp directories when the environment may restrict `%TEMP%` access;
- Token-counter tests must cover lazy loading, offline/download failure fallback, and cache-reuse behavior, not only happy-path exact counts;
- Run formatting, the stricter `basedpyright` wrapper, and the full pytest wrapper before finishing work.

## EDITING RULES

- Use ASCII unless the file already requires other characters;
- Keep comments sparse and only where they clarify non-obvious behavior;
- Do not hardcode configuration values across modules when a setting already exists;
- If a new customization knob is introduced, document it in `.env.example`;
- If a change affects contributor or agent workflow, update this file.

## PROJECT HABITS

- `src/` is the application source of truth;
- `data/` stores repo-local runtime assets that may be created or refreshed on demand, including the tokenizer model used by advanced token counting;
- `tests/` should remain unit-focused and cover regressions;
- `strings/en.json` centralizes user-facing strings and can reference locale-scoped resource files under `strings/en/*.res` for large text blocks;
- `.env.example` documents safe, non-secret local configuration and preference toggles;
- scripts under `scripts/` should resolve the repo root from their own location so they keep working after directory moves or when launched from outside the repository root;
- maintenance helpers under `scripts/` should prompt before destructive git actions, restore any required remotes automatically when possible, clean up generated temporary files when they are script-owned, and reject obvious no-op destructive operations;
- `README.md` should stay aligned with user-visible capabilities, controls, and configuration.

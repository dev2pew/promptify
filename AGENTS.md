# PROMPTIFY AGENT GUIDE

## SCOPE

- This repository targets modern Python and should stay compatible with the current project baseline in `pyproject.toml`;
- Prefer small, typed, test-backed refactors over broad speculative rewrites.

## CORE RULES

- Keep user-facing copy indexed from `strings/en.json`;
- In source code, always use string lookups with an inline fallback;
- Treat `strings/en.json` as the single source of truth for UI and message text, using resource references for large multiline blocks when needed;
- Route new environment configuration through `src/promptify/core/settings.py`;
- Invalid configuration values must never crash import-time startup. Fall back safely;
- Preserve Pylance basic type-checking cleanliness;
- Prefer shared helpers over repeated logic, especially in editor, resolver, and completion flows.
- Preserve terminal compatibility across modern terminals, classic Windows console hosts, and legacy `cmd.exe`; avoid assuming Unicode box-drawing support or safe full-screen behavior everywhere.

## TESTING RULES

Test using `$env:UV_CACHE_DIR='C:\Users\lucky\Documents\vscode\python\tools\dirs\ai\promptify\.uv-cache'; ./llt.bat` to avoid requiring elevation.

- Add or update unit tests for every behavioral change;
- Tests should assert localized text through `get_string(...)` instead of hardcoded copies when the value comes from `strings/en.json`;
- Keep tests deterministic and sandboxed;
- The test harness seeds `PROMPTIFY_*` values from `.env.example` through `tests/_settings_master.py` before importing application modules, so local `.env` tweaks must not influence test expectations;
- Settings-sensitive tests should reuse the generated passes from `tests/_settings_master.py` instead of hardcoding layout or render defaults; set `PROMPTIFY_TEST_PASS_COUNT` to control the number of generated passes, with a default of `4`;
- Run formatting and the full pytest wrapper before finishing work.

## EDITING RULES

- Use ASCII unless the file already requires other characters;
- Keep comments sparse and only where they clarify non-obvious behavior;
- Do not hardcode configuration values across modules when a setting already exists;
- If a new customization knob is introduced, document it in `.env.example`;
- If a change affects contributor or agent workflow, update this file.

## PROJECT HABITS

- `src/` is the application source of truth;
- `tests/` should remain unit-focused and cover regressions;
- `strings/en.json` centralizes user-facing strings and can reference locale-scoped resource files under `strings/en/` for large text blocks;
- `.env.example` documents safe, non-secret local configuration and preference toggles;
- `README.md` should stay aligned with user-visible capabilities, controls, and configuration.

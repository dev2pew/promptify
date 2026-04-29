# Promptify Agent Guide

## Scope

- This repository targets modern Python and should stay compatible with the current project baseline in `pyproject.toml`.
- Prefer small, typed, test-backed refactors over broad speculative rewrites.

## Core Rules

- Keep all user-facing copy in `strings/en.json`.
- In source code, always use string lookups with an inline fallback.
- Treat `strings/en.json` as the single source of truth for UI and message text.
- Route new environment configuration through `src/promptify/core/settings.py`.
- Invalid configuration values must never crash import-time startup. Fall back safely.
- Preserve Pylance basic type-checking cleanliness.
- Prefer shared helpers over repeated logic, especially in editor, resolver, and completion flows.

## Testing Rules

- Add or update unit tests for every behavioral change.
- Tests should assert localized text through `get_string(...)` instead of hardcoded copies when the value comes from `strings/en.json`.
- Keep tests deterministic and sandboxed.
- Run formatting and the full pytest wrapper before finishing work.

## Editing Rules

- Use ASCII unless the file already requires other characters.
- Keep comments sparse and only where they clarify non-obvious behavior.
- Do not hardcode configuration values across modules when a setting already exists.
- If a new customization knob is introduced, document it in `.env.example`.
- If a change affects contributor or agent workflow, update this file.

## Project Habits

- `src/` is the application source of truth.
- `tests/` should remain unit-focused and cover regressions.
- `strings/en.json` centralizes user-facing strings.
- `.env.example` documents safe, non-secret local configuration and preference toggles.

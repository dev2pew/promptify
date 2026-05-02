"""Shared persisted application state helpers"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import aiofiles


def _is_plain_int(value: object) -> bool:
    """Treat bools as invalid even though Python models them as ints"""
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(slots=True)
class AppState:
    """Mutable in-memory representation of persisted application state"""

    lastcase_index: int | None = None
    paths: dict[str, str] = field(default_factory=dict)
    modes: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: object) -> AppState:
        """Normalize untrusted JSON payloads into a typed application state"""
        if not isinstance(payload, dict):
            return cls()

        lastcase_index = payload.get("lastcase_index")
        raw_paths = payload.get("paths")
        raw_modes = payload.get("modes")
        paths = (
            {str(key): str(value) for key, value in raw_paths.items()}
            if isinstance(raw_paths, dict)
            else {}
        )
        modes = (
            {
                str(key): value
                for key, value in raw_modes.items()
                if _is_plain_int(value)
            }
            if isinstance(raw_modes, dict)
            else {}
        )
        return cls(
            lastcase_index=lastcase_index if _is_plain_int(lastcase_index) else None,
            paths=paths,
            modes=modes,
        )

    def to_payload(self) -> dict[str, object]:
        """Serialize the typed state into a JSON-safe dictionary"""
        return {
            "lastcase_index": self.lastcase_index,
            "paths": self.paths,
            "modes": self.modes,
        }

    def get_last_path(self, case_name: str) -> str:
        """Return the last target path remembered for the given case"""
        return self.paths.get(case_name, "")

    def save_last_path(self, case_name: str, path: str) -> None:
        """Remember the last target path used for the given case"""
        self.paths[case_name] = path

    def get_last_case_index(self, case_count: int) -> int | None:
        """Return the saved 1-based case index when it still fits the list"""
        index = self.lastcase_index
        if not _is_plain_int(index):
            return None
        if index < 1 or index > case_count:
            return None
        return index

    def save_last_case_index(self, index: int) -> None:
        """Remember the currently selected 1-based case index"""
        self.lastcase_index = index

    def get_last_mode(self, case_key: str) -> int | None:
        """Return the saved mode when it matches one of the supported ids"""
        mode = self.modes.get(case_key)
        return mode if mode in (1, 2) else None

    def save_last_mode(self, case_key: str, mode: int) -> None:
        """Remember the last selected mode for the given case key"""
        self.modes[case_key] = mode


@dataclass(slots=True, frozen=True)
class AppStateStore:
    """Load and save persisted application state from disk"""

    state_file: Path

    async def load(self) -> AppState:
        """Read the current state file, falling back safely on invalid content"""
        if self.state_file.exists():
            try:
                async with aiofiles.open(self.state_file, "r", encoding="utf-8") as f:
                    return AppState.from_payload(json.loads(await f.read()))
            except Exception:
                pass
        return AppState()

    async def save(self, state: AppState) -> None:
        """Write the given state back to disk"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.state_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(state.to_payload(), indent=4))

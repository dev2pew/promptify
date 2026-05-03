"""Shared persisted application state helpers"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeGuard, cast

import aiofiles


def _is_plain_int(value: object) -> TypeGuard[int]:
    """Treat bools as invalid even though Python models them as ints"""
    return isinstance(value, int) and not isinstance(value, bool)


async def _write_text_atomic(path: Path, text: str) -> None:
    """Write text to disk through a temporary file, then replace atomically"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
        await f.write(text)
    temp_path.replace(path)


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
        payload_map = cast(Mapping[str, Any], payload)

        lastcase_index = payload_map.get("lastcase_index")
        raw_paths = payload_map.get("paths")
        raw_modes = payload_map.get("modes")
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
class EditorSessionState:
    """Represent the restorable interactive-editor session snapshot"""

    case_dir: str
    target_path: str
    prompt_text: str
    version: int = 1

    @classmethod
    def from_payload(cls, payload: object) -> EditorSessionState | None:
        """Normalize an untrusted restore payload into a typed session state"""
        if not isinstance(payload, dict):
            return None
        payload_map = cast(Mapping[str, Any], payload)
        case_dir = payload_map.get("case_dir")
        target_path = payload_map.get("target_path")
        prompt_text = payload_map.get("prompt_text")
        version = payload_map.get("version", 1)
        if not isinstance(case_dir, str) or not isinstance(target_path, str):
            return None
        if not isinstance(prompt_text, str) or not _is_plain_int(version):
            return None
        return cls(
            case_dir=case_dir,
            target_path=target_path,
            prompt_text=prompt_text,
            version=version,
        )

    def to_payload(self) -> dict[str, object]:
        """Serialize the editor restore payload into JSON-safe data"""
        return {
            "version": self.version,
            "case_dir": self.case_dir,
            "target_path": self.target_path,
            "prompt_text": self.prompt_text,
        }


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
        await _write_text_atomic(
            self.state_file,
            json.dumps(state.to_payload(), indent=4),
        )


@dataclass(slots=True, frozen=True)
class EditorSessionStateStore:
    """Load, save, and remove the restorable editor session snapshot"""

    state_file: Path

    async def load(self) -> EditorSessionState | None:
        """Load the current editor session restore payload when present"""
        if not self.state_file.exists():
            return None
        try:
            async with aiofiles.open(self.state_file, "r", encoding="utf-8") as f:
                payload = json.loads(await f.read())
        except Exception:
            return None
        return EditorSessionState.from_payload(payload)

    async def save(self, state: EditorSessionState) -> None:
        """Persist the latest editor session restore payload"""
        await _write_text_atomic(
            self.state_file,
            json.dumps(state.to_payload(), indent=4),
        )

    async def delete(self) -> None:
        """Remove the persisted editor session restore payload if it exists"""
        try:
            self.state_file.unlink(missing_ok=True)
        except Exception:
            pass

"""Core dataclasses used by the `promptify` engine"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True, kw_only=True)
class FileMeta:
    """Store indexed metadata for a single file"""

    path: Path
    rel_path: str
    ext: str
    size: int
    mtime: float


@dataclass(slots=True, kw_only=True)
class CachedContent:
    """Store cached file content together with its modification time"""

    text: str
    mtime: float

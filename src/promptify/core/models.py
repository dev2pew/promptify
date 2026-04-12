from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True, kw_only=True)
class FileMeta:
    """Represents core file metadata mapped in the project index."""

    path: Path
    rel_path: str
    ext: str
    size: int
    mtime: float


@dataclass(slots=True, kw_only=True)
class CachedContent:
    """Stores cached file contents linked to a specific modification time."""

    text: str
    mtime: float

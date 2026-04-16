"""
CORE DATA STRUCTURES AND DATACLASSES FOR THE PROMPTIFY ENGINE.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True, kw_only=True)
class FileMeta:
    """
    REPRESENTS CORE FILE METADATA MAPPED IN THE PROJECT INDEX.
    DESIGNED EFFICIENTLY VIA __SLOTS__ EXECUTION.
    """

    path: Path
    rel_path: str
    ext: str
    size: int
    mtime: float


@dataclass(slots=True, kw_only=True)
class CachedContent:
    """
    STORES CACHED FILE CONTENTS LINKED TO A SPECIFIC MODIFICATION TIME.
    PROVIDES MEMORY-SAFETY VALIDATION FOR RAPID I/O ACCESSES.
    """

    text: str
    mtime: float

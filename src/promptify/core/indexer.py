"""
Asynchronous file system watcher and indexer.
Maintains an in-memory representation of the project to enable ultra-fast fuzzy matching.
"""

import asyncio
import os
import fnmatch
from pathlib import Path
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from ..ui.logger import log
from .models import FileMeta
from .config import CaseConfig
from ..utils.i18n import strings

type FileIndex = dict[str, FileMeta]


class ProjectIndexer(FileSystemEventHandler):
    """
    Maintains an in-memory, rapidly searchable index of project files.
    Utilizes watchdog to keep metadata strictly synchronized.
    """

    def __init__(self, target_dir: Path, case: CaseConfig):
        """
        Binds the indexer tracking to a specific project.

        Args:
            target_dir (Path): The working root directory to scan.
            case (CaseConfig): Ignore rules defining standard boundaries.
        """
        self.target_dir = target_dir
        self.case = case
        self.spec = case.get_ignore_spec(target_dir)

        self.files_by_rel: FileIndex = {}
        self.dirs: set[str] = set()

        self._observer = None
        self._lock = asyncio.Lock()

    async def build_index(self) -> None:
        """Initial fast scan using native OS scandir mappings."""
        log.info(strings["indexing_project"].format(name=self.target_dir.name))

        def _scan(directory: Path):
            try:
                with os.scandir(directory) as it:
                    for entry in it:
                        path = Path(entry.path)

                        if not self.case.is_file_allowed(
                            path, self.target_dir, self.spec
                        ):
                            continue

                        rel_path_str = str(path.relative_to(self.target_dir)).replace(
                            "\\", "/"
                        )

                        if entry.is_dir():
                            self.dirs.add(rel_path_str)
                            _scan(path)
                        elif entry.is_file():
                            stat = entry.stat()
                            self.files_by_rel[rel_path_str] = FileMeta(
                                path=path,
                                rel_path=rel_path_str,
                                ext=path.suffix.lstrip(".").lower(),
                                size=stat.st_size,
                                mtime=stat.st_mtime,
                            )
            except PermissionError:
                pass

        await asyncio.to_thread(_scan, self.target_dir)
        log.success(
            strings["indexed_success"].format(
                files=len(self.files_by_rel), dirs=len(self.dirs)
            )
        )

    def start_watching(self) -> None:
        """Bootstraps Watchdog, falling back to Polling for network/container mounts."""
        try:
            self._observer = Observer()
            self._observer.schedule(self, str(self.target_dir), recursive=True)
            self._observer.start()
        except Exception as e:
            log.warning(strings["observer_fallback"].format(error=e))
            self._observer = PollingObserver()
            self._observer.schedule(self, str(self.target_dir), recursive=True)
            self._observer.start()

    def stop_watching(self) -> None:
        """Gracefully joins and stops the Watchdog background worker thread."""
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def on_any_event(self, event: FileSystemEvent) -> None:
        """
        Thread-safe state update triggered automatically by filesystem changes.

        Args:
            event (FileSystemEvent): Generated OS file operation token.
        """
        src_path_str = getattr(event, "src_path", None)
        if not src_path_str:
            return

        path = Path(src_path_str).resolve()
        target = self.target_dir.resolve()

        if not path.is_relative_to(target):
            return

        rel_path_str = str(path.relative_to(target)).replace("\\", "/")
        is_dir = getattr(event, "is_directory", False)
        match_path = rel_path_str + ("/" if is_dir else "")

        if self.spec.match_file(match_path):
            return

        event_type = getattr(event, "event_type", "")

        if event_type in ("deleted", "moved"):
            if not is_dir:
                self.files_by_rel.pop(rel_path_str, None)
            else:
                self.dirs.discard(rel_path_str)

        if event_type in ("created", "modified", "moved"):
            dest_path_str = getattr(event, "dest_path", None)
            dest_path = Path(dest_path_str).resolve() if dest_path_str else path

            if dest_path.exists():
                dest_rel = str(dest_path.relative_to(target)).replace("\\", "/")

                if not self.case.is_file_allowed(dest_path, target, self.spec):
                    return

                if dest_path.is_file():
                    stat = dest_path.stat()
                    self.files_by_rel[dest_rel] = FileMeta(
                        path=dest_path,
                        rel_path=dest_rel,
                        ext=dest_path.suffix.lstrip(".").lower(),
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                    )
                else:
                    self.dirs.add(dest_rel)

    def find_matches(self, query: str) -> list[FileMeta]:
        """
        Supports exact, globbing, and fuzzy partial path matching.

        Args:
            query (str): Searching criterion path parameter.

        Returns:
            list[FileMeta]: Re-ordered array with the closest elements prioritised.
        """
        query = query.replace("\\", "/")

        if query in self.files_by_rel:
            return [self.files_by_rel[query]]

        if "*" in query or "?" in query or "**" in query:
            return [
                meta
                for p, meta in self.files_by_rel.items()
                if fnmatch.fnmatch(p, query) or Path(p).match(query)
            ]

        query_lower = query.lower()
        matches = [
            meta for p, meta in self.files_by_rel.items() if query_lower in p.lower()
        ]

        matches.sort(
            key=lambda m: (m.path.name.lower() != query_lower, len(m.rel_path))
        )
        return matches

    def get_by_extensions(self, exts: list[str]) -> list[FileMeta]:
        """
        Fetches all files terminating in specific formats.

        Args:
            exts (list[str]): File formats mapped strictly by their extension structure.

        Returns:
            list[FileMeta]: Aggregation of valid paths.
        """
        exts_clean = {e.strip().lstrip(".").lower() for e in exts}
        return [m for m in self.files_by_rel.values() if m.ext in exts_clean]

    def get_all_extensions(self) -> list[str]:
        """
        Returns all unique extensions currently loaded in the index.

        Returns:
            list[str]: Sorted extensions.
        """
        return sorted(list({m.ext for m in self.files_by_rel.values() if m.ext}))

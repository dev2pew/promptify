"""
ASYNCHRONOUS FILE SYSTEM WATCHER AND INDEXER.
MAINTAINS AN IN-MEMORY REPRESENTATION OF THE PROJECT TO ENABLE ULTRA-FAST FUZZY MATCHING.
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
from .matching import normalize_match_path, rank_path_candidates
from .settings import APP_SETTINGS
from ..utils.i18n import get_string

type FileIndex = dict[str, FileMeta]


class ProjectIndexer(FileSystemEventHandler):
    """
    MAINTAINS AN IN-MEMORY, RAPIDLY SEARCHABLE INDEX OF PROJECT FILES.
    UTILIZES WATCHDOG TO KEEP METADATA STRICTLY SYNCHRONIZED.
    """

    def __init__(self, target_dir: Path, case: CaseConfig):
        """
        BINDS THE INDEXER TRACKING TO A SPECIFIC PROJECT.

        Args:
            `target_dir` (Path): The working root directory to scan.
            `case` (CaseConfig): Ignore rules defining standard boundaries.
        """
        self.target_dir = target_dir
        self.case = case
        self.spec = case.get_ignore_spec(target_dir)

        self.files_by_rel: FileIndex = {}
        self.dirs: set[str] = set()
        self.revision = 0

        self._observer = None
        self._lock = asyncio.Lock()

    async def build_index(self) -> None:
        """Build the initial index using a fast directory scan"""
        log.info(
            get_string("indexing_project", "indexing - {name}").format(
                name=self.target_dir.name
            )
        )

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
        self.revision += 1
        log.success(
            get_string("indexed_success", "indexing done").format(
                files=len(self.files_by_rel), dirs=len(self.dirs)
            )
        )

    def start_watching(self) -> None:
        """Start filesystem watching, falling back to polling when needed"""
        watch_mode = APP_SETTINGS.indexer.watch_mode
        if watch_mode == "off":
            return

        try:
            self._observer = (
                PollingObserver() if watch_mode == "polling" else Observer()
            )
            self._observer.schedule(self, str(self.target_dir), recursive=True)
            self._observer.start()
        except Exception as err:
            if watch_mode == "native":
                raise
            log.warn(get_string("observer_fallback", "observer failed").format(e=err))
            self._observer = PollingObserver()
            self._observer.schedule(self, str(self.target_dir), recursive=True)
            self._observer.start()

    def stop_watching(self) -> None:
        """Stop the watchdog observer and wait for it to exit"""
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def on_any_event(self, event: FileSystemEvent) -> None:
        """
        THREAD-SAFE STATE UPDATE TRIGGERED AUTOMATICALLY BY FILESYSTEM CHANGES.

        Args:
            `event` (FileSystemEvent): Generated OS file operation token.
        """
        src_path_str = getattr(event, "src_path", None)
        if not src_path_str:
            return
        self.revision += 1

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
        SUPPORTS EXACT, GLOBBING, AND FUZZY PARTIAL PATH MATCHING.

        Args:
            `query` (str): Searching criterion path parameter.

        Returns:
            `list` [FileMeta]: Re-ordered array with the closest elements prioritised.
        """
        query = normalize_match_path(query)

        if query in self.files_by_rel:
            return [self.files_by_rel[query]]

        if "*" in query or "?" in query or "**" in query:
            return [
                meta
                for p, meta in self.files_by_rel.items()
                if fnmatch.fnmatch(p, query) or Path(p).match(query)
            ]

        ranked_paths = rank_path_candidates(query, list(self.files_by_rel.keys()))
        return [self.files_by_rel[path] for path in ranked_paths]

    def get_by_extensions(self, exts: list[str]) -> list[FileMeta]:
        """
        FETCHES ALL FILES TERMINATING IN SPECIFIC FORMATS.

        Args:
            `exts` (list[str]): File formats mapped strictly by their extension structure.

        Returns:
            `list` [FileMeta]: Aggregation of valid paths.
        """
        exts_clean = {e.strip().lstrip(".").lower() for e in exts}
        return [m for m in self.files_by_rel.values() if m.ext in exts_clean]

    def get_all_extensions(self) -> list[str]:
        """
        RETURNS ALL UNIQUE EXTENSIONS CURRENTLY LOADED IN THE INDEX.

        Returns:
            `list` [str]: Sorted extensions.
        """
        return sorted(list({m.ext for m in self.files_by_rel.values() if m.ext}))

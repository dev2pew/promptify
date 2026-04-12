import asyncio
import os
import fnmatch
from pathlib import Path
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from logger import log
from models import FileMeta
from config import CaseConfig

class ProjectIndexer(FileSystemEventHandler):
    """
    Maintains an in-memory, rapidly searchable index of project files.
    Utilizes watchdog to keep metadata strictly synchronized.
    """
    def __init__(self, target_dir: Path, case: CaseConfig):
        self.target_dir = target_dir
        self.case = case
        self.spec = case.get_ignore_spec(target_dir)

        self.files_by_rel: dict[str, FileMeta] = {}
        self.dirs: set[str] = set()

        self._observer = None
        self._lock = asyncio.Lock()

    async def build_index(self) -> None:
        """Initial fast scan using os.scandir."""
        log.info(f"indexing project - '{self.target_dir.name}'")

        def _scan(directory: Path):
            try:
                with os.scandir(directory) as it:
                    for entry in it:
                        path = Path(entry.path)
                        rel_path_str = str(path.relative_to(self.target_dir)).replace("\\", "/")

                        # Apply ignores
                        match_path = rel_path_str + ("/" if entry.is_dir() else "")
                        if self.spec.match_file(match_path):
                            continue

                        if entry.is_dir():
                            self.dirs.add(rel_path_str)
                            _scan(path)
                        elif entry.is_file():
                            if self.case.types and "*" not in self.case.types:
                                if path.suffix not in self.case.types:
                                    continue

                            stat = entry.stat()
                            self.files_by_rel[rel_path_str] = FileMeta(
                                path=path,
                                rel_path=rel_path_str,
                                ext=path.suffix.lstrip(".").lower(),
                                size=stat.st_size,
                                mtime=stat.st_mtime
                            )
            except PermissionError:
                pass

        await asyncio.to_thread(_scan, self.target_dir)
        log.success(f"indexed {len(self.files_by_rel)} files and {len(self.dirs)} directories")

    def start_watching(self) -> None:
        """Bootstraps Watchdog, falling back to Polling for network/container mounts."""
        try:
            self._observer = Observer()
            self._observer.schedule(self, str(self.target_dir), recursive=True)
            self._observer.start()
        except Exception as e:
            log.warning(f"standard observer failed, falling back to 'PollingObserver' - {e}")
            self._observer = PollingObserver()
            self._observer.schedule(self, str(self.target_dir), recursive=True)
            self._observer.start()

    def stop_watching(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Thread-safe state update triggered by filesystem changes."""
        path = Path(event.src_path)
        try:
            if not path.is_relative_to(self.target_dir):
                return

            rel_path_str = str(path.relative_to(self.target_dir)).replace("\\", "/")
            match_path = rel_path_str + ("/" if event.is_directory else "")

            if self.spec.match_file(match_path):
                return

            if event.event_type in ("deleted", "moved"):
                if not event.is_directory:
                    self.files_by_rel.pop(rel_path_str, None)
                else:
                    self.dirs.discard(rel_path_str)

            if event.event_type in ("created", "modified", "moved"):
                dest_path = Path(event.dest_path) if hasattr(event, "dest_path") else path

                if dest_path.exists():
                    dest_rel = str(dest_path.relative_to(self.target_dir)).replace("\\", "/")
                    if dest_path.is_file():
                        stat = dest_path.stat()
                        self.files_by_rel[dest_rel] = FileMeta(
                            path=dest_path,
                            rel_path=dest_rel,
                            ext=dest_path.suffix.lstrip(".").lower(),
                            size=stat.st_size,
                            mtime=stat.st_mtime
                        )
                    else:
                        self.dirs.add(dest_rel)
        except Exception:
            pass

    def find_matches(self, query: str) -> list[FileMeta]:
        """Supports exact, globbing, and fuzzy partial path matching."""
        query = query.replace("\\", "/")

        # 1. Exact Match
        if query in self.files_by_rel:
            return [self.files_by_rel[query]]

        # 2. Glob Match
        if "*" in query or "?" in query or "**" in query:
            return [
                meta for p, meta in self.files_by_rel.items()
                if fnmatch.fnmatch(p, query) or Path(p).match(query)
            ]

        # 3. Fuzzy Partial Match (e.g. app.ts -> src/app/app.ts)
        query_lower = query.lower()
        matches = [
            meta for p, meta in self.files_by_rel.items()
            if query_lower in p.lower()
        ]

        # Score exact basename hits higher
        matches.sort(key=lambda m: (m.path.name.lower() != query_lower, len(m.rel_path)))
        return matches

    def get_by_extensions(self, exts: list[str]) -> list[FileMeta]:
        exts_clean = {e.strip().lstrip('.').lower() for e in exts}
        return [m for m in self.files_by_rel.values() if m.ext in exts_clean]

    def get_all_extensions(self) -> list[str]:
        return sorted(list({m.ext for m in self.files_by_rel.values() if m.ext}))

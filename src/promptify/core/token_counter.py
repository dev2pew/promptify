"""Shared asynchronous token counting helpers"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import blake2b
from pathlib import Path
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

try:
    import regex
    import tiktoken
    from tiktoken import Encoding
    from tiktoken.load import load_tiktoken_bpe
except ImportError:
    regex = None
    tiktoken = None

_DEFAULT_CACHE_SIZE = 64
_DEFAULT_PIECE_CACHE_SIZE = 8192
_MODEL_DOWNLOAD_URL = (
    "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
)
_MODEL_DOWNLOAD_TIMEOUT_SECONDS = 5.0
_MODEL_RETRY_COOLDOWN_SECONDS = 30.0
_O200K_ENCODING_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "o200k_base.tiktoken"
)
_O200K_SPECIAL_TOKENS = {"<|endoftext|>": 199999, "<|endofprompt|>": 200018}
_O200K_PATTERN = "|".join(
    [
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""\p{N}{1,3}""",
        r""" ?[^\s\p{L}\p{N}]+[\r\n/]*""",
        r"""\s*[\r\n]+""",
        r"""\s+(?!\S)""",
        r"""\s+""",
    ]
)


@dataclass(frozen=True, slots=True)
class TokenizerRuntime:
    """Prepared exact-tokenizer state shared across resolver instances"""

    encoding: Encoding
    piece_pattern: regex.Pattern[str]


class _CountCancelled(Exception):
    """Internal cooperative cancellation sentinel for worker-thread counts"""


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: TokenizerRuntime | None = None
_LAST_PREPARE_FAILURE = 0.0


def _fingerprint_text(text: str) -> bytes:
    """Create a compact stable cache key without retaining full text copies"""
    return blake2b(text.encode("utf-8"), digest_size=16).digest()


def _download_model_file(path: Path) -> bool:
    """Download the tokenizer model into the shared repo-local data directory"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with urlopen(
            _MODEL_DOWNLOAD_URL, timeout=_MODEL_DOWNLOAD_TIMEOUT_SECONDS
        ) as src:
            temp_path.write_bytes(src.read())
        temp_path.replace(path)
        return True
    except (OSError, TimeoutError, URLError):
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _ensure_model_file(path: Path) -> bool:
    """Ensure the exact-tokenizer model file exists, downloading it on demand"""
    global _LAST_PREPARE_FAILURE

    if path.is_file():
        return True

    now = time.monotonic()
    if now - _LAST_PREPARE_FAILURE < _MODEL_RETRY_COOLDOWN_SECONDS:
        return False

    if _download_model_file(path):
        return True

    _LAST_PREPARE_FAILURE = now
    return False


def _load_runtime() -> TokenizerRuntime | None:
    """Load and cache the exact-tokenizer runtime once for the whole process"""
    global _RUNTIME
    global _LAST_PREPARE_FAILURE

    if _RUNTIME is not None:
        return _RUNTIME
    if tiktoken is None or regex is None:
        return None

    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            return _RUNTIME
        if not _ensure_model_file(_O200K_ENCODING_PATH):
            return None
        try:
            mergeable_ranks = load_tiktoken_bpe(str(_O200K_ENCODING_PATH))
            _RUNTIME = TokenizerRuntime(
                encoding=Encoding(
                    name="o200k_base",
                    pat_str=_O200K_PATTERN,
                    mergeable_ranks=mergeable_ranks,
                    special_tokens=_O200K_SPECIAL_TOKENS,
                ),
                piece_pattern=regex.compile(_O200K_PATTERN),
            )
        except Exception:
            _LAST_PREPARE_FAILURE = time.monotonic()
            return None
        return _RUNTIME


class AsyncTokenCounter:
    """Count tokens off the event loop with cache and in-flight de-duplication"""

    def __init__(
        self,
        enabled: bool,
        cache_size: int = _DEFAULT_CACHE_SIZE,
        piece_cache_size: int = _DEFAULT_PIECE_CACHE_SIZE,
    ):
        self._enabled = enabled
        self._cache_size = max(1, cache_size)
        self._piece_cache_size = max(1, piece_cache_size)
        self._cache: OrderedDict[bytes, int] = OrderedDict()
        self._piece_cache: OrderedDict[bytes, int] = OrderedDict()
        self._inflight: dict[bytes, asyncio.Task[int]] = {}
        self._lock = asyncio.Lock()
        self._piece_cache_lock = threading.Lock()

    @property
    def is_enabled(self) -> bool:
        """Report whether exact token counting is configured"""
        return self._enabled

    async def count(self, text: str) -> int:
        """Count tokens asynchronously while reusing cached work"""
        if not self._enabled:
            raise RuntimeError("exact token counting is disabled")

        key = _fingerprint_text(text)
        async with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached

            task = self._inflight.get(key)
            if task is None:
                cancel_event = threading.Event()
                task = asyncio.create_task(
                    asyncio.to_thread(self._count_sync, text, cancel_event)
                )
                task.add_done_callback(lambda _task: cancel_event.set())
                self._inflight[key] = task
                owner = True
            else:
                owner = False

        try:
            count = await task
        except asyncio.CancelledError:
            if owner:
                task.cancel()
            raise
        finally:
            if owner:
                async with self._lock:
                    self._inflight.pop(key, None)

        if owner:
            async with self._lock:
                self._cache[key] = count
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)

        return count

    def _count_sync(self, text: str, cancel_event: threading.Event) -> int:
        """Run exact tokenization in a worker thread with cooperative cancellation"""
        runtime = _load_runtime()
        if runtime is None:
            raise RuntimeError("exact token counting is not available")

        total = 0
        matched = False
        for index, match in enumerate(runtime.piece_pattern.finditer(text)):
            matched = True
            if index % 128 == 0 and cancel_event.is_set():
                raise _CountCancelled()
            total += self._count_piece(runtime, match.group(0))

        if not matched and text:
            if cancel_event.is_set():
                raise _CountCancelled()
            return len(runtime.encoding.encode_ordinary(text))

        return total

    def _count_piece(self, runtime: TokenizerRuntime, piece: str) -> int:
        """Count one tokenizer regex piece and reuse the shared local cache"""
        key = _fingerprint_text(piece)
        with self._piece_cache_lock:
            cached = self._piece_cache.get(key)
            if cached is not None:
                self._piece_cache.move_to_end(key)
                return cached

        count = len(runtime.encoding.encode_ordinary(piece))
        with self._piece_cache_lock:
            self._piece_cache[key] = count
            self._piece_cache.move_to_end(key)
            while len(self._piece_cache) > self._piece_cache_size:
                self._piece_cache.popitem(last=False)
        return count

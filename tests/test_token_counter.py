"""Tests for asynchronous exact token counting"""

import asyncio
from pathlib import Path
import shutil
import time
from types import SimpleNamespace

import pytest

import promptify.core.token_counter as token_counter_module
from promptify.core.token_counter import AsyncTokenCounter


@pytest.mark.asyncio
async def test_async_token_counter_caches_completed_results(monkeypatch):
    """Repeated exact counts should reuse the completed cache entry"""
    counter = AsyncTokenCounter(True)
    calls = 0

    def fake_count(text: str, _cancel_event) -> int:
        nonlocal calls
        calls += 1
        return len(text)

    monkeypatch.setattr(counter, "_count_sync", fake_count)

    first = await counter.count("alpha beta")
    second = await counter.count("alpha beta")

    assert first == second == len("alpha beta")
    assert calls == 1


@pytest.mark.asyncio
async def test_async_token_counter_deduplicates_inflight_requests(monkeypatch):
    """Concurrent requests for the same text should share one worker task"""
    counter = AsyncTokenCounter(True)
    calls = 0

    def fake_count(text: str, _cancel_event) -> int:
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return len(text) + 1

    monkeypatch.setattr(counter, "_count_sync", fake_count)

    first, second = await asyncio.gather(
        counter.count("shared text"),
        counter.count("shared text"),
    )

    assert first == second == len("shared text") + 1
    assert calls == 1


@pytest.mark.asyncio
async def test_async_token_counter_does_not_prepare_runtime_during_init(monkeypatch):
    """Constructing the counter should stay cheap until the first real count"""
    calls = 0

    def fake_load_runtime():
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            encoding=SimpleNamespace(encode_ordinary=lambda text: list(text)),
            piece_pattern=SimpleNamespace(finditer=lambda text: ()),
        )

    monkeypatch.setattr(token_counter_module, "_load_runtime", fake_load_runtime)

    counter = AsyncTokenCounter(True)

    assert calls == 0
    assert await counter.count("alpha") == 5
    assert calls == 1


def test_ensure_model_file_downloads_when_missing(monkeypatch):
    """The advanced tokenizer should fetch the model when the target file is absent"""
    target = Path("tests/.model-download-success/data/o200k_base.tiktoken")
    calls = 0

    def fake_download(path):
        nonlocal calls
        calls += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("model", encoding="utf-8")
        return True

    monkeypatch.setattr(token_counter_module, "_last_prepare_failure_at", 0.0)
    monkeypatch.setattr(token_counter_module, "_download_model_file", fake_download)

    try:
        assert token_counter_module._ensure_model_file(target)
        assert target.is_file()
        assert calls == 1
    finally:
        shutil.rmtree(target.parents[1], ignore_errors=True)


def test_ensure_model_file_returns_false_after_failed_download(monkeypatch):
    """When the download fails, exact mode should fall back instead of crashing"""
    target = Path("tests/.model-download-fail/data/o200k_base.tiktoken")

    monkeypatch.setattr(token_counter_module, "_last_prepare_failure_at", 0.0)
    monkeypatch.setattr(
        token_counter_module, "_download_model_file", lambda _path: False
    )

    try:
        assert not token_counter_module._ensure_model_file(target)
    finally:
        shutil.rmtree(target.parents[1], ignore_errors=True)

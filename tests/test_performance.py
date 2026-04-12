import pytest
import time

pytestmark = pytest.mark.asyncio


async def test_concurrent_resolution(app_components):
    """Tests resolving a large number of tags concurrently to ensure TaskGroup handles it fast."""
    _, resolver = app_components

    # Create a prompt with 100 mentions of app.py
    prompt = " ".join(["<@file:app.py>"] * 100)

    start = time.perf_counter()
    res = await resolver.resolve_user(prompt)
    duration = time.perf_counter() - start

    # It should resolve very quickly due to TaskGroup and caching
    assert duration < 2.0
    assert res.count("This is line 1") == 100

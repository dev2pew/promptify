import pytest
import time

pytestmark = pytest.mark.asyncio


async def test_concurrent_resolution(app_components):
    """Tests resolving a large number of tags concurrently to ensure TaskGroup handles it fast."""
    _, resolver = app_components

    # CREATE A PROMPT WITH 100 MENTIONS OF APP.PY
    prompt = " ".join(["<@file:app.py>"] * 100)

    start = time.perf_counter()
    res = await resolver.resolve_user(prompt)
    duration = time.perf_counter() - start

    # IT SHOULD RESOLVE VERY QUICKLY DUE TO TASKGROUP AND CACHING
    assert duration < 2.0

    # "THIS IS LINE 1'" (WITH QUOTE) APPEARS EXACTLY ONCE PER FILE.
    # WE CHECK FOR THE QUOTE TO AVOID MATCHING "THIS IS LINE 10", "11", ETC.
    assert res.count("This is line 1'") == 100

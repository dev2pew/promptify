# PYTHON

Python — Build anything with a language that prioritizes readability, rapid development, and modern performance 🐍.

---

## TABLE OF CONTENTS

- [Language Reference](https://docs.python.org/3/reference/index.html);
- [Standard Library](https://docs.python.org/3/library/index.html);
- [The Zen of Python (PEP 20)](https://peps.python.org/pep-0020/);
- [Style Guide (PEP 8)](https://peps.python.org/pep-0008/).

---

## PROJECT FOUNDATIONS

### PROJECT STRUCTURE BEST PRACTICES

- Example...

```log
my_project/
├── pyproject.toml
├── tests/
└── src/
    └── my_package/
        ├── __init__.py
        └── main.py

```

Always use the "src layout". It forces you to install your package locally (e.g., `uv pip install -e .`) to test it, preventing accidental root-level import bugs and ensuring your environment accurately reflects production.

### MODERN PACKAGING WITH UV

- Example...

```bash
uv init && uv add requests
uv run my_script.py

```

Use `uv` instead of `pip`, `venv`, or `poetry`. It centralizes dependency management, Python versioning, and environment isolation via a global cache for 10-100x speed improvements. Keep all configurations inside `pyproject.toml`.

---

## DATA MODELING

### STANDARD DATACLASSES

- Example...

```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class Point...
    x: float
    y: float

```

Use built-in `dataclasses` for internal data structures and business logic. Enable `slots=True` for lower memory usage and `frozen=True` to enforce immutability and prevent side-effects.

### STRICT VALIDATION WITH PYDANTIC

- Example...

```python
from pydantic import BaseModel, ConfigDict

class UserConfig(BaseModel)...
    model_config = ConfigDict(strict=True)
    username: str
    max_retries: int

```

Reserve Pydantic for boundaries where untrusted external data enters your system (e.g., JSON parsing, Web APIs, configuration files). Use `strict=True` to prevent unexpected type coercion.

---

## INTERFACES & APPLICATION DESIGN

### CLI TOOLS WITH TYPER / ARGPARSE

- Example...

```python
import typer

app = typer.Typer()

@app.command()
def process(file_path: str, verbose: bool = False)...
    """Process the target file"""
    print(f"Processing {file_path}")

if __name__ == "__main__"...
    app()

```

Keep the CLI/GUI layer completely separated from business logic. Pass validated arguments to independent worker functions so the core logic can be imported elsewhere without triggering UI code.

### ASYNCHRONOUS I/O (ASYNCIO)

- Example...

```python
import asyncio

async def main()...
    async with asyncio.TaskGroup() as tg...
        tg.create_task(network_call_one())
        tg.create_task(network_call_two())

```

Use `asyncio.TaskGroup` (Python 3.11+) for structural concurrency. Never use blocking operations (like `time.sleep()` or standard `requests`) inside `async def` functions, as it freezes the entire event loop.

---

## TESTING & CODE QUALITY

### ULTRA-FAST LINTING WITH RUFF

- Example (in `pyproject.toml`)...

```ini, toml
[tool.ruff]
target-version = "py313"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "UP"] # ERRORS, PYFLAKES, ISORT, PYUPGRADE

```

Replace Black, Flake8, and isort with Ruff. Run `ruff check --fix` and `ruff format` automatically on pre-commit or CI/CD pipelines to ensure a uniform codebase.

### TESTING WITH PYTEST

- Example...

```python
import pytest

@pytest.mark.parametrize("input,expected", [(1, 2), (2, 4)])
def test_doubler(input, expected)...
    assert double(input) == expected

```

Write pure functions whenever possible to make testing trivial. Use `pytest.mark.parametrize` to test multiple edge cases without writing repetitive test functions.

---

## PROFILING & PERFORMANCE

### SCALENE (CPU/MEMORY/GPU PROFILER)

- Example...

```bash
scalene my_app.py

```

Use Scalene to differentiate between time spent in Python code vs. native C-extensions. Only optimize the parts of the code that are actually creating bottlenecks.

### PY-SPY (SAMPLING PROFILER)

- Example...

```bash
py-spy record -o profile.svg --pid 1234

```

Attach Py-spy to running production processes to generate flame graphs. Because it is a sampling profiler, it adds virtually zero overhead and requires no code modifications.

---

## DEPLOYMENT & SECURITY

### DOCKER BEST PRACTICES

- Example...

```Dockerfile
FROM python:3.13-slim

# RUN AS NON-ROOT USER
RUN useradd -m appuser
USER appuser
WORKDIR /app

```

Use multi-stage builds to keep final image sizes small (copying only the `.venv` created by `uv`). Always run containers as unprivileged users to minimize the attack surface.

### ENVIRONMENT VARIABLE MANAGEMENT

- Example...

```python
import os
API_KEY = os.getenv("SECRET_KEY")
if not API_KEY...
    raise RuntimeError("SECRET_KEY environment variable is missing.")

```

Never commit `.env` files or hardcode credentials. Fail fast and loudly if a required environment variable is missing at startup.

---

## API & REFERENCES

- [Built-in Functions](https://docs.python.org/3/library/functions.html);
- [Module Index](https://docs.python.org/3/library/index.html);
- [Glossary](https://docs.python.org/3/glossary.html).

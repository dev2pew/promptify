# PROMPT

complete the task while adhering to the guidelines after analyzing the project structure and its contents.

## TASK

TODO: [[YOUR_TASK_HERE]]

## GUIDE

- provide `uv` commands if needed; (for environment syncing, dependency management, or project execution)
- leverage Python 3.13+ features; (free-threaded interpreter/No GIL, JIT compilation, and modern REPL)
- ensure structured concurrency and robust error handling; (`asyncio.TaskGroup`, `ExceptionGroup`, and `asyncio.timeout`)
- utilize modern type parameter syntax (PEP 695) and strict Pydantic validation; (`strict=True`, `frozen=True`)
- prefer modular architecture and the `src/` layout; (FastAPI `APIRouter`, dependency injection, and discrete schemas)
- manage the project using modern tooling; (use `pyproject.toml` and `uv.lock`, avoiding legacy `requirements.txt`)
- follow official Python best practices and secure containerization guidelines; (multi-stage Docker builds, non-privileged users)
- ensure AI-ready structural constraints. (unified abstraction layers and schema-validated LLM outputs)

## TREE

below is the project structure...

```log
[@project]
```

## NOTE

TODO: [[YOUR_NOTES_HERE]]

## CONTEXT

below is the project files contents...

<@dir:/>

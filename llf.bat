@ECHO OFF
TITLE %~n0

ECHO [i] linting and fixing...
uv.exe run ruff check --fix %* src/

ECHO [i] formatting...
uv.exe run ruff format src/ %* tests/

ECHO [+] all done.

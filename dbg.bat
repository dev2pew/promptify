@ECHO OFF
TITLE %~n0
SETLOCAL

SET PYTHONFAULTHANDLER=1
SET PYTHONUNBUFFERED=1
SET PYDEVD_DISABLE_FILE_VALIDATION=1

uv.exe run --with debugpy python -X dev -Xfrozen_modules=off -m debugpy --listen 5678 --wait-for-client -m promptify %*

PAUSE

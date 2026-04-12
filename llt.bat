@ECHO OFF
TITLE %~n0

uv.exe run pytest -v %*

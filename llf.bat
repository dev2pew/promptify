@ECHO OFF
TITLE %~n0

uv.exe run black --target-version py313 src/

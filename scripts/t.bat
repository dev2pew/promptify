@ECHO OFF
TITLE %~n0

PUSHD "%~dp0.."
uv.exe run pytest -v %*
SET "EXIT_CODE=%ERRORLEVEL%"
POPD
EXIT /B %EXIT_CODE%

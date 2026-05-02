@ECHO OFF
TITLE %~n0

PUSHD "%~dp0.."
uvx.exe --from basedpyright basedpyright "src\" "tests\"
SET "EXIT_CODE=%ERRORLEVEL%"
POPD

PAUSE
EXIT /B %EXIT_CODE%

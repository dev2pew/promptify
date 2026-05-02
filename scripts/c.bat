@ECHO OFF
TITLE %~n0

SET "ROOT=%~dp0"
SET "RES=%~dp0data"

IF NOT EXIST "%RES%" (
    MKDIR "%RES%"
)

SET "OUT=%RES%\problems.json"
SET "RAW=%TEMP%\promptify-llc-%RANDOM%%RANDOM%.json"

PUSHD "%ROOT%"

uv.exe run --with basedpyright basedpyright --outputjson src tests > "%RAW%"
uv.exe run python "%~dp0c.py" "%RAW%" "%OUT%" "%ROOT%"

SET "EXIT=%ERRORLEVEL%"

IF EXIST "%RAW%" (
    DEL "%RAW%"
)

POPD
EXIT /B %EXIT%

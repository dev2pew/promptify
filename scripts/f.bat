@ECHO OFF
TITLE %~n0

PUSHD "%~dp0.."
SET "CHECK_ONLY=0"
IF "%~1"=="--check" (
    SET "CHECK_ONLY=1"
    SHIFT
)

IF "%CHECK_ONLY%"=="1" GOTO :CHECK

ECHO [i] linting and fixing...
uv.exe run ruff check --fix scripts/ src/ tests/ %*
IF ERRORLEVEL 1 GOTO :DONE

ECHO [i] formatting...
uv.exe run ruff format scripts/ src/ tests/ %*
IF ERRORLEVEL 1 GOTO :DONE

ECHO [+] all done.
GOTO :DONE

:CHECK
ECHO [i] linting...
uv.exe run ruff check scripts/ src/ tests/ %*
IF ERRORLEVEL 1 GOTO :DONE

ECHO [i] checking formatting...
uv.exe run ruff format --check scripts/ src/ tests/ %*
IF ERRORLEVEL 1 GOTO :DONE

ECHO [+] all done.

:DONE
SET "EXIT_CODE=%ERRORLEVEL%"
POPD
EXIT /B %EXIT_CODE%

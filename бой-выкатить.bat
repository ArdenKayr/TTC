@echo off
rem Deploy the current commit to PRODUCTION (/opt/ttc) - live users are affected.
rem The script refuses to run unless the very same commit was deployed to the
rem test environment first, and it asks for a typed confirmation.
rem
rem NOTE: keep the contents of this file ASCII-only. "chcp 65001" switches the
rem console codepage mid-file, and cmd.exe re-reads the remaining bytes with
rem the new codepage - any Cyrillic text below this point would be garbled and
rem then executed as commands. All Russian output comes from Python instead.
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=py"
)

%PY% -m scripts.deploy prod

echo.
pause

@echo off
rem Build the user guide page for Telegraph and open it in a browser.
rem Just double-click this file.
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

%PY% -m scripts.build_user_guide
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

start "" "docs\USER_GUIDE.html"

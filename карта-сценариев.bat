@echo off
rem Пересобрать карту сценариев из кода и открыть её в браузере.
rem Двойной клик по этому файлу — всё, что нужно.
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=py"
)

echo Собираю карту сценариев из кода...
%PY% -m scripts.build_scenario_map
if errorlevel 1 (
    echo.
    echo ================================================================
    echo  Карта НЕ собрана. Сообщение об ошибке — выше.
    echo  Обычная причина: в коде что-то переименовали или удалили,
    echo  а в docs\scenario-map.json это ещё не отражено.
    echo ================================================================
    echo.
    pause
    exit /b 1
)

echo Открываю...
start "" "docs\scenario-map.html"

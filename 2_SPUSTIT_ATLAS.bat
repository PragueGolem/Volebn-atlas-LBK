@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist "%~dp0index.html" (
  echo CHYBI index.html ve slozce:
  echo %~dp0
  echo.
  echo Spust tento BAT z korenove slozky rozbaleneho atlasu.
  pause
  exit /b 1
)

if not exist "%~dp0results.json" (
  echo Data jeste nejsou vytvorena.
  echo Nejdriv spust 1_VYTVORIT_DATA.bat.
  pause
  exit /b 1
)
if not exist "%~dp0precincts_kv2022.geojson" (
  echo Chybi geometrie okrsku 2022. Nejdriv spust 1_VYTVORIT_DATA.bat.
  pause
  exit /b 1
)
if not exist "%~dp0precincts_kv2026_liberec.geojson" (
  echo Chybi geometrie okrsku 2026. Nejdriv spust 1_VYTVORIT_DATA.bat.
  pause
  exit /b 1
)

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py"
if defined PYTHON_CMD goto pythonok
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"
if not defined PYTHON_CMD goto nopython

:pythonok
echo Pracovni slozka: %~dp0
echo.
echo Atlas bude na:
echo http://localhost:8000/index.html
echo.
start "" "http://localhost:8000/index.html"
%PYTHON_CMD% -m http.server 8000 --directory "%~dp0"
exit /b 0

:nopython
echo Python 3 nebyl nalezen.
pause
exit /b 2

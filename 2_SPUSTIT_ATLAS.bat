@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist "%~dp0public\data\results.json" (
  echo Data jeste nejsou vytvorena.
  echo Nejdriv spust 1_VYTVORIT_DATA.bat z ROZBALENE slozky atlasu.
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
start "" "http://localhost:8000"
echo Atlas bezi na http://localhost:8000
echo Toto okno nech otevrene. Ukoncis ho Ctrl+C.
%PYTHON_CMD% -m http.server 8000 -d "%~dp0public"
exit /b 0

:nopython
echo Python 3 nebyl nalezen.
pause
exit /b 2

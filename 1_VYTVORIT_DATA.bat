@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ==============================================
echo   VOLEBNI ATLAS LIBERCE 2022-2026 - DATA
echo ==============================================
echo.

if not exist "%~dp0build_data.py" goto missingfiles

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
echo Stahuji a pripravuji oficialni volebni data CSU pro Liberec...
%PYTHON_CMD% "%~dp0build_data.py"
if errorlevel 1 goto builderror

echo.
echo ==============================================
echo HOTOVO.
echo Ted spust 2_SPUSTIT_ATLAS.bat
echo ==============================================
pause
exit /b 0

:missingfiles
echo CHYBI build_data.py.
echo Tento BAT spust z cele rozbalene slozky projektu.
pause
exit /b 2

:nopython
echo Python 3 nebyl nalezen.
pause
exit /b 3

:builderror
echo.
echo Priprava dat selhala. Posli posledni radky chyby do ChatGPT.
pause
exit /b 5

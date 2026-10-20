@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo VOLEBNI ATLAS LIBERCE - SPUSTENI V2
echo ==========================================
echo.

echo Pracovni slozka:
echo %cd%
echo.

if not exist "index.html" (
  echo CHYBA: index.html v teto slozce neni.
  echo Obsah slozky:
  dir /b
  echo.
  echo Hledam index.html ve vnorenych slozkach...
  for /r %%F in (index.html) do (
    echo Nalezeno: %%~dpF
    cd /d "%%~dpF"
    goto found
  )
  echo index.html nebyl nikde nalezen.
  pause
  exit /b 1
)

:found
echo.
echo Server bude spusten ze slozky:
echo %cd%
echo.
if not exist "index.html" (
  echo CHYBA: index.html stale neni v aktualni slozce.
  pause
  exit /b 2
)

echo Overeni souboru:
dir index.html

echo.
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py"
if defined PYTHON_CMD goto pythonok
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"
if not defined PYTHON_CMD goto nopython

:pythonok
echo.
echo Atlas bude na:
echo http://127.0.0.1:8000/index.html
echo.
start "" "http://127.0.0.1:8000/index.html"
%PYTHON_CMD% -m http.server 8000 --bind 127.0.0.1
exit /b 0

:nopython
echo Python 3 nebyl nalezen.
pause
exit /b 3

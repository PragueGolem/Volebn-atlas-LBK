@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ==============================================
echo   VOLEBNI ATLAS LIBERECKEHO KRAJE - DATA
echo ==============================================
echo.

if not exist "%~dp0requirements.txt" goto missingfiles
if not exist "%~dp0build_data.py" goto missingfiles

rem Resolve ONE concrete Python executable and use exactly the same
rem interpreter for pip installation and for build_data.py. This avoids a
rem Windows py-launcher/shebang mismatch between Python versions.
set "PYTHON_EXE="
where py >nul 2>nul
if not errorlevel 1 (
  for /f "usebackq delims=" %%I in (`py -c "import sys; print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
)
if defined PYTHON_EXE goto pythonok

where python >nul 2>nul
if not errorlevel 1 (
  for /f "usebackq delims=" %%I in (`python -c "import sys; print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
)
if not defined PYTHON_EXE goto nopython

:pythonok
echo Pracovni slozka: %~dp0
echo Python: "%PYTHON_EXE%"
echo.
echo Instaluji / kontroluji Python balicky...
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto piperror

echo.
echo Overuji, ze balicky vidi stejny Python...
"%PYTHON_EXE%" -c "import sys, pandas, pyproj; print('OK - Python', sys.version.split()[0], '| pandas', pandas.__version__, '| pyproj', pyproj.__version__)"
if errorlevel 1 goto importerror

echo.
echo Stahuji a pripravuji oficialni volebni data CSU...
"%PYTHON_EXE%" "%~dp0build_data.py"
if errorlevel 1 goto builderror

echo.
echo ==============================================
echo HOTOVO.
echo Ted spust 2_SPUSTIT_ATLAS.bat
echo ==============================================
pause
exit /b 0

:missingfiles
echo CHYBI SOUBORY PROJEKTU.
echo.
echo Tento soubor musi byt spusten z ROZBALENE cele slozky atlasu.
echo Nespoustej ho primo uvnitr ZIP archivu a nekopiruj samotny BAT jinam.
echo.
echo Ocekavam zde napr.:
echo   %~dp0requirements.txt
echo   %~dp0build_data.py
pause
exit /b 2

:nopython
echo Python 3 nebyl nalezen.
echo Nainstaluj Python 3 a pri instalaci zaskrtni Add Python to PATH.
pause
exit /b 3

:piperror
echo.
echo Instalace Python balicku selhala. Python byl nalezen, ale pip vratil chybu.
pause
exit /b 4

:importerror
echo.
echo Balicky se nainstalovaly, ale stejny Python je neumi importovat.
echo Posli mi prosim cely vypis z tohoto okna vcetne radku "Python:".
pause
exit /b 6

:builderror
echo.
echo Priprava dat selhala. Posli mi prosim text chyby z tohoto okna.
pause
exit /b 5

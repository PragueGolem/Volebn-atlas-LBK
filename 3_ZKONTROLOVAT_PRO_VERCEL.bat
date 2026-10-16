@echo off
setlocal
cd /d "%~dp0"
echo ==============================================
echo   KONTROLA DAT PRO VERCEL
echo ==============================================
echo.
if not exist "public\index.html" goto :missing
if not exist "public\app.js" goto :missing
if not exist "public\data\metadata.json" goto :nodata
if not exist "public\data\results.json" goto :nodata
if not exist "public\data\precincts_kz2024.geojson" goto :nodata
if not exist "public\data\precincts_ps2025.geojson" goto :nodata
if not exist "public\data\precincts_kv2026.geojson" goto :nodata
echo OK. Projekt ma aplikaci i vygenerovana data.
echo Muze jit na GitHub a nasledne na Vercel.
goto :end
:missing
echo CHYBA: chybi soubory webove aplikace ve slozce public.
goto :end
:nodata
echo CHYBI DATA: nejdriv spust 1_VYTVORIT_DATA.bat.
:end
echo.
pause

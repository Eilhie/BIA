@echo off
title OMSET OUTLET PIPELINE
echo ============================================================
echo   OMSET OUTLET PIPELINE - GENERATOR OTOMATIS
echo ============================================================
echo.

cd /d "%~dp0"

echo [1] Transpose UMUM   (DAPUL + LAPUL)
echo [2] Transpose HOREKA
echo [3] Transpose SEMUA  (UMUM + HOREKA)
echo [4] Keluar
echo.
set /p PILIHAN="Pilih (1/2/3/4): "

if "%PILIHAN%"=="1" (
    echo.
    echo Transpose UMUM: DAPUL + LAPUL...
    python transpose.py umum
    goto :end
)
if "%PILIHAN%"=="2" (
    echo.
    echo Transpose HOREKA...
    python transpose.py horeka
    goto :end
)
if "%PILIHAN%"=="3" (
    echo.
    echo Transpose semua...
    python transpose.py all
    goto :end
)
if "%PILIHAN%"=="4" goto :eof

:end
echo.
echo Pipeline selesai. Output tersimpan di folder: output\
echo.
pause

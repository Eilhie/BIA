@echo off
setlocal enabledelayedexpansion
title AMBIL DATA BARU - OMSHAR

set "ERROR_LOG=D:\SDAAREA\SKU_Terlewat.txt"
set "DB_DIR=D:\SDAAREA\DB"

echo ==================================================
echo   AMBIL DATA BARU
echo   %date% %time%
echo ==================================================
echo.

:: ==================================================
:: STEP 1: SYNC OMSHAR DARI SERVER
:: ==================================================
echo [STEP 1/2] Sinkronisasi OMSHAR dari server...
echo.

call "D:\SDAAREA\SYNC OMSHAR FAST.bat" nopause

:: ==================================================
:: QUALITY CHECK - ringkasan sebelum lanjut transpose
:: ==================================================
echo.
echo ==================================================
echo   RINGKASAN SYNC
echo ==================================================

if exist "%ERROR_LOG%" (
    echo.
    echo [!] SKU berikut tidak ditemukan di server:
    echo.
    type "%ERROR_LOG%"
    echo.
    echo     Cek apakah nama SKU berubah atau file belum tersedia.
    echo     Transpose tetap bisa dijalankan untuk SKU yang berhasil.
) else (
    echo [OK] Semua SKU berhasil disync. Tidak ada yang terlewat.
)

echo.
echo   3 file OMSHAR terbaru di DB (indikator freshness data):
powershell -command "Get-ChildItem 'D:\SDAAREA\DB\*.xls' | Sort-Object LastWriteTime -Desc | Select-Object -First 3 | ForEach-Object { Write-Host ('    ' + $_.LastWriteTime.ToString('dd MMM yyyy  HH:mm') + '   ' + $_.Name) }"
echo.

:: ==================================================
:: STEP 2: TRANSPOSE
:: ==================================================
echo ==================================================
echo   [STEP 2/2] TRANSPOSE
echo   Konversi XLS -> CSV untuk query Python.
echo ==================================================
echo.
echo   [1] UMUM   (DAPUL + LAPUL)
echo   [2] HOREKA
echo   [3] SEMUA  (UMUM + HOREKA)
echo   [4] Lewati - transpose nanti
echo.
set /p PILIHAN="Pilih (1/2/3/4): "

if "%PILIHAN%"=="4" goto :selesai
if "%PILIHAN%"=="1" ( set "TRANS_MODE=umum"   & goto :run_transpose )
if "%PILIHAN%"=="2" ( set "TRANS_MODE=horeka" & goto :run_transpose )
if "%PILIHAN%"=="3" ( set "TRANS_MODE=all"    & goto :run_transpose )

echo Pilihan tidak dikenali, lewati transpose.
goto :selesai

:run_transpose
echo.
echo Menjalankan: python transpose.py %TRANS_MODE%
echo.
cd /d "D:\SDAAREA\omset_pipeline"
python transpose.py %TRANS_MODE%
cd /d "D:\SDAAREA"

:selesai
echo.
echo ==================================================
echo   SELESAI - %date% %time%
echo ==================================================
pause
exit /b 0

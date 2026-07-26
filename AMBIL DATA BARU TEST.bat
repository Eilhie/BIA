@echo off
setlocal enabledelayedexpansion
title AMBIL DATA BARU - TEST MODE

:: ==================================================
:: Semua path diarahkan ke D:\SDAAREA\test\
:: Tidak menyentuh D:\DB OMSHAR\ sama sekali.
:: ==================================================

set "TEST_ROOT=D:\SDAAREA\test"
set "TEST_DB=%TEST_ROOT%\DB"
set "TEST_OUT=%TEST_ROOT%\output\DB TRANSPOSED"
set "TEST_CSV=%TEST_ROOT%\output\CSV"
set "TEST_LOG=%TEST_ROOT%\sync_log.txt"
set "TEST_ERR=%TEST_ROOT%\SKU_Terlewat.txt"

set "SRC_SERVER=\\10.4.1.25\Bev\OMSHAR"
set "LIST_DIR=D:\DB OMSHAR\SKU_LIST"
set "CLEAN_DIR=%TEMP%\OMSHAR_TEST_TEMP"

echo ==================================================
echo   AMBIL DATA BARU  [TEST MODE]
echo   Semua output -^> D:\SDAAREA\test\
echo   %date% %time%
echo ==================================================
echo.

:: Buat folder test jika belum ada
if not exist "%TEST_DB%"  mkdir "%TEST_DB%"
if not exist "%TEST_OUT%" mkdir "%TEST_OUT%"
if not exist "%TEST_CSV%" mkdir "%TEST_CSV%"

if exist "%TEST_ERR%" del "%TEST_ERR%"
set "TERLEWAT_COUNT=0"

:: ==================================================
:: STEP 1: SYNC OMSHAR ke folder TEST (bukan D:\DB OMSHAR\DB)
:: ==================================================
echo [STEP 1/2] Sync OMSHAR ke folder test...
echo.

if not exist "%SRC_SERVER%" (
    echo [ERROR] Server tidak dapat diakses. Cek VPN/Jaringan.
    pause & exit /b 1
)
if not exist "%LIST_DIR%" (
    echo [ERROR] Folder SKU_LIST tidak ditemukan.
    pause & exit /b 1
)

:: Pre-process SKU list
if exist "%CLEAN_DIR%" rd /s /q "%CLEAN_DIR%"
mkdir "%CLEAN_DIR%\UMUM"
mkdir "%CLEAN_DIR%\HOREKA"

for %%F in ("%LIST_DIR%\UMUM\*.txt") do (
    powershell -command "$l=Get-Content '%%F'; if($l){$c=$l|%%{$_.Trim()}|?{$_}; if($c){[IO.File]::WriteAllLines('%CLEAN_DIR%\UMUM\%%~nxF',$c)}}"
)
for %%F in ("%LIST_DIR%\HOREKA\*.txt") do (
    powershell -command "$l=Get-Content '%%F'; if($l){$c=$l|%%{$_.Trim()}|?{$_}; if($c){[IO.File]::WriteAllLines('%CLEAN_DIR%\HOREKA\%%~nxF',$c)}}"
)

for %%C in (UMUM HOREKA) do (
    if exist "%CLEAN_DIR%\%%C\*.txt" (
        echo   Kategori: %%C
        for %%F in ("%CLEAN_DIR%\%%C\*.txt") do (
            set "FILE_LIST="
            set "BRAND_COUNT=0"
            for /f "usebackq delims=" %%P in ("%%~fF") do (
                set FILE_LIST=!FILE_LIST! "OMSHAR %%C %%P.xls"
                set /a BRAND_COUNT+=1
            )
            if !BRAND_COUNT! gtr 0 (
                robocopy "%SRC_SERVER%" "%TEST_DB%" !FILE_LIST! /XO /R:1 /W:1 /MT:8 /NP /NDL /NJH /NJS
                for /f "usebackq delims=" %%P in ("%%~fF") do (
                    if not exist "%TEST_DB%\OMSHAR %%C %%P.xls" (
                        echo   [TIDAK ADA] OMSHAR %%C %%P.xls
                        echo [%%C] OMSHAR %%C %%P.xls >> "%TEST_ERR%"
                        set /a TERLEWAT_COUNT+=1
                    )
                )
            )
        )
    )
)

if exist "%CLEAN_DIR%" rd /s /q "%CLEAN_DIR%"

echo [%date% %time%] Sync selesai. Terlewat: %TERLEWAT_COUNT% >> "%TEST_LOG%"

:: ==================================================
:: RINGKASAN SYNC
:: ==================================================
echo.
echo ==================================================
echo   RINGKASAN SYNC (test)
echo ==================================================

set /a TOTAL_XLS=0
for %%F in ("%TEST_DB%\*.xls") do set /a TOTAL_XLS+=1
echo   File XLS di test\DB : %TOTAL_XLS% file

if exist "%TEST_ERR%" (
    echo   [!] SKU tidak ditemukan:
    type "%TEST_ERR%"
) else (
    echo   [OK] Semua SKU berhasil disync ke test\DB.
)

echo.
echo   3 file terbaru di test\DB:
powershell -command "Get-ChildItem '%TEST_DB%\*.xls' | Sort-Object LastWriteTime -Desc | Select-Object -First 3 | ForEach-Object { Write-Host ('    ' + $_.LastWriteTime.ToString('dd MMM yyyy  HH:mm') + '   ' + $_.Name) }"
echo.

:: ==================================================
:: STEP 2: TRANSPOSE dari test\DB -> test\output
:: ==================================================
echo ==================================================
echo   [STEP 2/2] TRANSPOSE (output -> test\output\)
echo ==================================================
echo.
echo   [1] UMUM   (DAPUL + LAPUL)
echo   [2] HOREKA
echo   [3] SEMUA  (UMUM + HOREKA)
echo   [4] Lewati
echo.
set /p PILIHAN="Pilih (1/2/3/4): "

if "%PILIHAN%"=="4" goto :selesai
if "%PILIHAN%"=="1" ( set "TRANS_MODE=umum"   & goto :run_transpose )
if "%PILIHAN%"=="2" ( set "TRANS_MODE=horeka" & goto :run_transpose )
if "%PILIHAN%"=="3" ( set "TRANS_MODE=all"    & goto :run_transpose )
echo Pilihan tidak dikenali, lewati.
goto :selesai

:run_transpose
echo.
echo   OMSHAR_DIR     = %TEST_DB%
echo   TRANSPOSE_OUT  = %TEST_OUT%
echo   TRANSPOSE_CSV  = %TEST_CSV%
echo.

set "OMSHAR_DIR=%TEST_DB%"
set "TRANSPOSE_OUT=%TEST_OUT%"
set "TRANSPOSE_CSV=%TEST_CSV%"

cd /d "D:\SDAAREA\omset_pipeline"
python transpose.py %TRANS_MODE%
cd /d "D:\SDAAREA"

:selesai
echo.
echo ==================================================
echo   SELESAI [TEST MODE] - %date% %time%
echo   Output ada di: %TEST_ROOT%\
echo ==================================================
pause
exit /b 0

@echo off
setlocal enabledelayedexpansion

:: ==================================================
:: SYNC OMSHAR FAST - Robocopy Multi-Thread
:: Versi cepat dari COPY OMSHAR BIA.bat (~4-6x lebih cepat)
::
:: Perbedaan utama:
::   - Robocopy /MT:8 : copy paralel 8 thread sekaligus
::   - /XO            : skip file yang sudah up-to-date (tanpa stat per file)
::   - 1 panggilan robocopy per brand (bukan per SKU)
::   - Cek "terlewat" dilakukan lokal setelah sync (bukan ke server)
:: ==================================================

set "SRC_SERVER=\\10.4.1.25\Bev\OMSHAR"
set "DEST_BASE=D:\DB OMSHAR\DB"
set "LIST_DIR=D:\DB OMSHAR\SKU_LIST"
set "ERROR_LOG=D:\SDAAREA\SKU_Terlewat.txt"
set "SYNC_LOG=D:\SDAAREA\sync_log.txt"
set "CLEAN_DIR=%TEMP%\OMSHAR_SYNC_TEMP"

if exist "%ERROR_LOG%" del "%ERROR_LOG%"
set "TERLEWAT_COUNT=0"

echo [%date% %time%] ========== SYNC FAST DIMULAI ========== >> "%SYNC_LOG%"

echo ==================================================
echo   SYNC OMSHAR FAST  (Robocopy /MT:8)
echo   Waktu: %date% %time%
echo ==================================================
echo.

:: ---- Validasi ----
if not exist "%LIST_DIR%" (
    echo [ERROR] Folder SKU_LIST tidak ditemukan: %LIST_DIR%
    pause
    exit /b 1
)
if not exist "%SRC_SERVER%" (
    echo [ERROR] Server tidak dapat diakses. Cek VPN/Jaringan.
    pause
    exit /b 1
)
if not exist "%DEST_BASE%" mkdir "%DEST_BASE%"

:: ---- Pre-process: bersihkan file SKU (trim + hapus baris kosong) ----
if exist "%CLEAN_DIR%" rd /s /q "%CLEAN_DIR%"
mkdir "%CLEAN_DIR%\UMUM"
mkdir "%CLEAN_DIR%\HOREKA"

for %%F in ("%LIST_DIR%\UMUM\*.txt") do (
    powershell -command "$l=Get-Content '%%F'; if($l){$c=$l|%%{$_.Trim()}|?{$_}; if($c){[IO.File]::WriteAllLines('%CLEAN_DIR%\UMUM\%%~nxF',$c)}}"
)
for %%F in ("%LIST_DIR%\HOREKA\*.txt") do (
    powershell -command "$l=Get-Content '%%F'; if($l){$c=$l|%%{$_.Trim()}|?{$_}; if($c){[IO.File]::WriteAllLines('%CLEAN_DIR%\HOREKA\%%~nxF',$c)}}"
)

:: ==================================================
:: SYNC PER KATEGORI (UMUM lalu HOREKA)
:: ==================================================
for %%C in (UMUM HOREKA) do (
    if exist "%CLEAN_DIR%\%%C\*.txt" (
        echo ==================================================
        echo   KATEGORI: %%C
        echo ==================================================
        echo.

        for %%F in ("%CLEAN_DIR%\%%C\*.txt") do (
            set "BRAND_NAME=%%~nF"
            set "FILE_LIST="
            set "BRAND_COUNT=0"

            :: Akumulasi semua filename SKU untuk brand ini
            for /f "usebackq delims=" %%P in ("%%~fF") do (
                set FILE_LIST=!FILE_LIST! "OMSHAR %%C %%P.xls"
                set /a BRAND_COUNT+=1
            )

            if !BRAND_COUNT! gtr 0 (
                echo   [ !BRAND_NAME! ]  (!BRAND_COUNT! SKU^)

                :: Satu panggilan robocopy untuk semua SKU brand ini
                robocopy "%SRC_SERVER%" "%DEST_BASE%" !FILE_LIST! /XO /R:1 /W:1 /MT:8 /NP /NDL /NJH /NJS

                echo [%date% %time%] [%%C] [!BRAND_NAME!] !BRAND_COUNT! SKU diproses >> "%SYNC_LOG%"

                :: Cek lokal mana yang tidak berhasil masuk (lebih cepat dari cek ke server)
                for /f "usebackq delims=" %%P in ("%%~fF") do (
                    if not exist "%DEST_BASE%\OMSHAR %%C %%P.xls" (
                        echo   [TIDAK ADA] OMSHAR %%C %%P.xls
                        echo [%%C] [!BRAND_NAME!] OMSHAR %%C %%P.xls tidak ditemukan - %date% %time% >> "%ERROR_LOG%"
                        set /a TERLEWAT_COUNT+=1
                    )
                )
                echo.
            )
        )
    )
)

:: Hapus temp
if exist "%CLEAN_DIR%" rd /s /q "%CLEAN_DIR%"

:: ==================================================
:: HASIL AKHIR
:: ==================================================
echo ==================================================
echo   SYNC SELESAI
echo   Terlewat : %TERLEWAT_COUNT% SKU
echo ==================================================
echo.

echo [%date% %time%] SELESAI - Terlewat: %TERLEWAT_COUNT% >> "%SYNC_LOG%"
echo. >> "%SYNC_LOG%"

if %TERLEWAT_COUNT% gtr 0 (
    powershell -command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Sync OMSHAR selesai dengan peringatan!`nTerlewat : %TERLEWAT_COUNT% SKU`n`nFile log terlewat akan dibuka.', 'OMSHAR FAST - Peringatan', 'OK', 'Warning')"
    notepad "%ERROR_LOG%"
) else (
    powershell -command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Sync OMSHAR FAST Sukses!`nSemua SKU UMUM + HOREKA lengkap.', 'OMSHAR FAST - Sukses', 'OK', 'Information')"
    if exist "%ERROR_LOG%" del "%ERROR_LOG%"
)

if /i not "%1"=="nopause" pause
exit /b 0

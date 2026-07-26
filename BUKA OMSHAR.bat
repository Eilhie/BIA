@echo off
setlocal enabledelayedexpansion
title BUKA FILE OMSHAR
set "DB=D:\DB OMSHAR\DB"
set "ADA=0"
set "TIDAK_ADA=0"

echo ==================================================
echo   BUKA FILE OMSHAR
echo   Sumber: %DB%
echo ==================================================
echo.
echo   [1] UMUM
echo   [2] HOREKA
echo   [3] Cek ketersediaan saja (tanpa buka)
echo   [4] Keluar
echo.
set /p PILIHAN="Pilih (1/2/3/4): "
echo.
if "%PILIHAN%"=="4" exit /b 0
if "%PILIHAN%"=="1" ( set "MODE=BUKA" & goto :umum   )
if "%PILIHAN%"=="2" ( set "MODE=BUKA" & goto :horeka )
if "%PILIHAN%"=="3" ( set "MODE=CEK"  & goto :cek_semua )
echo Pilihan tidak dikenali.
pause & exit /b 1

:: ==================================================
:: UMUM (exact dari tabel)
:: ==================================================
:umum
echo [UMUM] - %MODE%...
echo.
for %%S in (
    "KLW330W"
    "KLW500WH"
    "KLW330DK"
    "KLW640DK"
    "PAKC320L"
    "PAKP330L"
    "PKC320L"
    "PKP330L"
    "PKB620L"
    "PKEG30L"
    "PKC320P"
    "PCP330P"
    "PKP330P"
    "PKC500P"
    "PKB620P"
    "RPKEG30L"
    "RPKC320L"
    "RPKB330L"
    "RPCP330L"
    "RPCB620L"
    "RPKB620L"
    "SKC320P"
    "SCP330P"
    "SKP330P"
    "SKC500P"
    "SCPB620P"
    "SKB620PP"
    "SINGARAJA ARAK BREMER"
    "SINGARAJA ARAK JERUK MADU"
    "SKC500PM"
    "SKB620PM"
    "SKB620PS"
    "SKB620PT"
) do call :buka UMUM %%S
goto :selesai

:: ==================================================
:: HOREKA (exact dari tabel — beda: SAB620, SAJMP330, SKC620PM)
:: ==================================================
:horeka
echo [HOREKA] - %MODE%...
echo.
for %%S in (
    "KLW330W"
    "KLW500WH"
    "KLW330DK"
    "KLW640DK"
    "PAKC320L"
    "PAKP330L"
    "PKC320L"
    "PKP330L"
    "PKB620L"
    "PKEG30L"
    "PKC320P"
    "PCP330P"
    "PKP330P"
    "PKC500P"
    "PKB620P"
    "RPKEG30L"
    "RPKC320L"
    "RPKB330L"
    "RPCP330L"
    "RPCB620L"
    "RPKB620L"
    "SKC320P"
    "SCP330P"
    "SKP330P"
    "SKC500P"
    "SCPB620P"
    "SKB620PP"
    "SAB620"
    "SAJMP330"
    "SKC500PM"
    "SKC620PM"
    "SKB620PS"
    "SKB620PT"
) do call :buka HOREKA %%S
goto :selesai

:: ==================================================
:: CEK SEMUA
:: ==================================================
:cek_semua
set "MODE=CEK"
echo [UMUM]
for %%S in (
    "KLW330W" "KLW500WH" "KLW330DK" "KLW640DK"
    "PAKC320L" "PAKP330L"
    "PKC320L" "PKP330L" "PKB620L" "PKEG30L"
    "PKC320P" "PCP330P" "PKP330P" "PKC500P" "PKB620P"
    "RPKEG30L" "RPKC320L" "RPKB330L" "RPCP330L" "RPCB620L" "RPKB620L"
    "SKC320P" "SCP330P" "SKP330P" "SKC500P" "SCPB620P"
    "SKB620PP" "SINGARAJA ARAK BREMER" "SINGARAJA ARAK JERUK MADU"
    "SKC500PM" "SKB620PM" "SKB620PS" "SKB620PT"
) do call :buka UMUM %%S
echo.
echo [HOREKA]
for %%S in (
    "KLW330W" "KLW500WH" "KLW330DK" "KLW640DK"
    "PAKC320L" "PAKP330L"
    "PKC320L" "PKP330L" "PKB620L" "PKEG30L"
    "PKC320P" "PCP330P" "PKP330P" "PKC500P" "PKB620P"
    "RPKEG30L" "RPKC320L" "RPKB330L" "RPCP330L" "RPCB620L" "RPKB620L"
    "SKC320P" "SCP330P" "SKP330P" "SKC500P" "SCPB620P"
    "SKB620PP" "SAB620" "SAJMP330"
    "SKC500PM" "SKC620PM" "SKB620PS" "SKB620PT"
) do call :buka HOREKA %%S
goto :selesai

:: ==================================================
:buka
set "FILE=%DB%\OMSHAR %~1 %~2.xls"
if exist "%FILE%" (
    echo   [OK] OMSHAR %~1 %~2.xls
    set /a ADA+=1
    if "%MODE%"=="BUKA" start "" "%FILE%"
) else (
    echo   [--] OMSHAR %~1 %~2.xls
    set /a TIDAK_ADA+=1
)
goto :eof

:: ==================================================
:selesai
echo.
echo ==================================================
echo   Ditemukan : %ADA% file
echo   Tidak ada : %TIDAK_ADA% file
if %TIDAK_ADA% gtr 0 echo   File tidak ada = belum disync atau nama beda di server.
echo ==================================================
pause
exit /b 0

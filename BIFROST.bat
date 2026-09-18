@echo off
title Bifrost - Gerbang SDA

:menu
cls
echo ==================================================
echo   BIFROST -- Gerbang ke semua app SDA
echo ==================================================
echo.
echo   [1] Heimdall           (OMSET Seeker, localhost saja)
echo   [2] Heimdall (LAN)     (bisa diakses rekan kantor)
echo   [3] Heimdall (DEV)     (mode development, port 8502)
echo   [4] Mimir              (Wiki LLM lokal, port 8600)
echo   [5] Keluar
echo.
set /p PILIHAN="Pilih (1-5): "

if "%PILIHAN%"=="1" goto heimdall_local
if "%PILIHAN%"=="2" goto heimdall_lan
if "%PILIHAN%"=="3" goto heimdall_dev
if "%PILIHAN%"=="4" goto mimir
if "%PILIHAN%"=="5" exit /b 0
echo.
echo Pilihan tidak dikenali.
pause
goto menu

:heimdall_local
title Heimdall - OMSET Seeker
cd /d "D:\SDAAREA\omset-app"
echo.
echo Membuka Heimdall di browser (localhost saja, tidak ke internet)...
python -m streamlit run app.py --server.headless false --server.address localhost
goto end

:heimdall_lan
title Heimdall - OMSET Seeker (LAN)
cd /d "D:\SDAAREA\omset-app"
echo.
echo Mencari alamat IP lokal PC ini...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do set LOCAL_IP=%%a
set LOCAL_IP=%LOCAL_IP: =%
echo.
echo ============================================
echo   Heimdall - Mode LAN
echo   Rekan di jaringan kantor bisa akses lewat:
echo   http://%LOCAL_IP%:8501
echo   (kalau PC ini punya lebih dari satu adapter
echo    jaringan, cek "ipconfig" manual untuk pastikan
echo    IP yang benar)
echo.
echo   Sekarang butuh login (username/password per level akses
echo   0-5) -- menu yang tampil otomatis menyesuaikan level
echo   akun yang login, tidak semua halaman kebuka ke sembarang
echo   orang lagi. Tetap jangan bagikan alamat ini di luar
echo   jaringan kantor.
echo ============================================
echo.
python -m streamlit run app.py --server.headless false --server.address 0.0.0.0
goto end

:heimdall_dev
title Heimdall - DEV (isolated, port 8502)
cd /d "D:\SDAAREA-dev"
echo.
echo ==================================================
echo   Mode DEV -- terpisah total dari server produksi
echo   (D:\SDAAREA, port 8501). Folder/branch/database/
echo   output semuanya sendiri, tidak menyentuh yang live.
echo   Buka di: http://localhost:8502
echo ==================================================
echo.
python -m streamlit run app.py --server.headless false --server.address localhost --server.port 8502
goto end

:mimir
title Mimir - SDA Internal Wiki
cd /d "D:\SDAAREA\mimir"
echo.
echo Membuka Mimir di browser (localhost saja, tidak ke internet)...
venv\Scripts\python.exe -m streamlit run app.py --server.headless false --server.address localhost --server.port 8600
goto end

:end
pause

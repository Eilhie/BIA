@echo off
title CARI OUTLET - OMSET Seeker (LAN)
cd /d "D:\SDAAREA"

echo Mencari alamat IP lokal PC ini...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do set LOCAL_IP=%%a
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo ============================================
echo   OMSET Seeker - Mode LAN
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
pause

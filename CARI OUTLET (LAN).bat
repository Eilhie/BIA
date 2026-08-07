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
echo   PENTING: semua halaman termasuk Sync/Atur SKU/
echo   Cek Cutoff ikut kebuka ke siapa pun yang tahu
echo   alamat ini. Jangan bagikan di luar jaringan kantor.
echo ============================================
echo.

python -m streamlit run omset_search_app.py --server.headless false --server.address 0.0.0.0
pause

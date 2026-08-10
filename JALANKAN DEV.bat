@echo off
title OMSET Seeker - DEV (isolated, port 8502)
cd /d "D:\SDAAREA-dev"
echo ==================================================
echo   Mode DEV -- terpisah total dari server produksi
echo   (D:\SDAAREA, port 8501). Folder/branch/database/
echo   output semuanya sendiri, tidak menyentuh yang live.
echo   Buka di: http://localhost:8502
echo ==================================================
echo.
python -m streamlit run app.py --server.headless false --server.address localhost --server.port 8502
pause

@echo off
title CARI OUTLET - OMSET Seeker
cd /d "D:\SDAAREA"
echo Membuka OMSET Seeker di browser (localhost saja, tidak ke internet)...
python -m streamlit run app.py --server.headless false --server.address localhost
pause

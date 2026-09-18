@echo off
title Mimir - SDA Internal Wiki
cd /d "%~dp0"
echo Membuka Mimir di browser (localhost saja, tidak ke internet)...
venv\Scripts\python.exe -m streamlit run app.py --server.headless false --server.address localhost --server.port 8600
pause

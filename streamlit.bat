@echo off
title OracleBot Dashboard
cd /d "%~dp0"
python -m streamlit run gui/app.py --server.port 8501
pause

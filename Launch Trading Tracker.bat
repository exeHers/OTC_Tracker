@echo off
title OTC Trading Tracker
cd /d "%~dp0"

pip install -r requirements.txt -q 2>nul
python tracker.py

if errorlevel 1 (
    echo.
    pause
)

@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Create the game's Python environment first; see README.md.
 pause
 exit /b 1
)
.venv\Scripts\python.exe scripts\install_english_voices.py
pause

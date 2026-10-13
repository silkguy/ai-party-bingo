@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Create the virtual environment first; see README.md.
 pause
 exit /b 1
)
.venv\Scripts\python.exe launcher.py
pause

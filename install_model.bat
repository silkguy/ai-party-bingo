@echo off
cd /d "%~dp0"
where ollama >nul 2>&1
if errorlevel 1 (
 echo Ollama is not installed or is not on PATH.
 echo Install it from https://ollama.com/download, then reopen this installer.
 pause
 exit /b 1
)
echo Downloading qwen3:4b. Keep the Ollama desktop app running.
echo This needs internet once and may take a while.
ollama pull qwen3:4b
if errorlevel 1 (
 echo Download failed. Open Ollama, check your internet connection, then retry.
) else (
 echo Model ready! In game Settings ^> AI, choose qwen3:4b and click Check Ollama / Retry.
 echo Then press Resume in the conversation.
)
pause

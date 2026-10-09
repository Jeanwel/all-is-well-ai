@echo off
REM One-click start (Windows): starts Ollama if needed, warms up the model, starts the app, opens the browser.
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe run.py) else (python run.py)
pause

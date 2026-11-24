@echo off
REM TraceOPME - porta 8000
cd /d "%~dp0"
".venv\Scripts\python.exe" -m uvicorn src.main:app --port 8000
pause

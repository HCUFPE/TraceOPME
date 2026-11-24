@echo off
REM Cria o ambiente Python (.venv) e instala as dependencias do TraceOPME. Rode uma vez.
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import sys" 2>/dev/null || rmdir /s /q .venv
)
if not exist .venv\Scripts\python.exe py -m venv .venv || python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Pronto. Agora rode o rodar.bat
pause

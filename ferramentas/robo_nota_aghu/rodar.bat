@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call instalar.bat
.venv\Scripts\python robo_nota_aghu.py %1

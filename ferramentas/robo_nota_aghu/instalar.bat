@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py instalar.py) || (python instalar.py)

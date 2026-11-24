@echo off
rem Aberto pelo navegador quando se clica em "Lancar no AGHU" no TraceOPME.
cd /d "%~dp0"
.venv\Scripts\python robo_nota_aghu.py --link "%~1"

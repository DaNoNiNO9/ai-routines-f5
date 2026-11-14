@echo off
rem Doble clic: levanta la demo de Alza en produccion y copia la URL publica.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo_pro.ps1"
pause

@echo off
set HOME=%~dp0

set PYTHONPATH=%HOME%\..
%HOME%\..\venv\Scripts\python.exe -m build --wheel
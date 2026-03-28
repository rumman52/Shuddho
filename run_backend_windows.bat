@echo off
setlocal
cd /d "%~dp0"
py -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000 --reload

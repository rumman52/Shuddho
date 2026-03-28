@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=py"
)
%PYTHON% -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000 --reload

@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=py"
)

%PYTHON% -c "import sys; v=sys.version_info; print(f'[shuddho] Using Python {v.major}.{v.minor}.{v.micro}'); raise SystemExit(0 if (v.major, v.minor) >= (3, 11) else 1)"
if errorlevel 1 (
  echo [shuddho] Python 3.11 or newer is required. Python 3.11 is the recommended Windows setup.
  exit /b 1
)

%PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
if errorlevel 1 (
  echo [shuddho] Python 3.11 is the recommended Windows happy path for local detector and backend development.
)

if not exist ".env" (
  echo [shuddho] Warning: repo-root .env was not found. Copy .env.example to .env before starting if you need detector or corrector config.
)

%PYTHON% -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000 --reload

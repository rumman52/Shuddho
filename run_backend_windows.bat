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
) else (
  echo [shuddho] Loading repo-root .env from %cd%\.env
)

%PYTHON% -c "from services.api.shuddho_api.app import ALLOWED_ORIGINS, corrector_service, detector_service; print('[shuddho] Backend URL: http://127.0.0.1:8000'); detector=detector_service.runtime_status(); corrector=corrector_service.runtime_status(); print(f'[shuddho] Detector: status={detector.status} checkpoint={detector.checkpoint} exists={detector.checkpoint_exists}'); print(f'[shuddho] Corrector: status={corrector.status} checkpoint={corrector.checkpoint} exists={corrector.checkpoint_exists}'); print('[shuddho] Allowed origins: ' + ', '.join(ALLOWED_ORIGINS))"

%PYTHON% -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000 --reload

@echo off
setlocal
cd /d "%~dp0"

REM ===== Ansible UI launcher (Windows dev) =====
REM Port 5001 is used because 127.0.0.1:5000 is often taken by Logitech G HUB.
REM Change PORT below if 5001 conflicts too.

set "PORT=5001"
set "PYTHON=E:\Workspace\.ansible-ui-venv\Scripts\python.exe"
set "SHIM=%~dp0wincompat"

REM Primary admin account. MUST change for real deployment.
REM WARNING: this password also derives the key that encrypts stored host passwords.
REM Changing it makes existing saved host passwords undecryptable.
set "ADMIN_USERNAME=admin"
set "ADMIN_PASSWORD=admin123"

if not exist "%PYTHON%" (
  echo [ERROR] Python venv not found: %PYTHON%
  echo Create it first:
  echo   D:\Anaconda3\python.exe -m venv E:\Workspace\.ansible-ui-venv
  echo   E:\Workspace\.ansible-ui-venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  pause
  exit /b 1
)

if not exist "%SHIM%" (
  echo [WARN] Windows compat shim not found: %SHIM%
  echo        ansible 6.7 needs grp/pwd/fcntl/termios shims on Windows.
)

set "PYTHONPATH=%SHIM%"

echo ============================================================
echo  Ansible UI starting...
echo  Open:  http://127.0.0.1:%PORT%
echo  Admin: %ADMIN_USERNAME%
echo  Stop:  Ctrl+C
echo ============================================================
echo.

"%PYTHON%" app.py

echo.
echo Server stopped.
pause

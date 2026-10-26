@echo off
setlocal EnableExtensions
TITLE MRI - Integrated Candidate Launcher

REM ============================================================================
REM  MRI launcher for the INTEGRATED CANDIDATE (run.py mri).
REM
REM  Differences vs the old launcher (which ran app\mri_dashboard\mri_api.py):
REM    * starts `run.py mri`  -> loopback 127.0.0.1 + MANDATORY authentication
REM    * validates credentials BEFORE starting (fails closed, never unauthenticated)
REM    * sets TEMP/TMP before Playwright/Chromium is ever launched
REM    * waits for the port to listen BEFORE opening the browser
REM    * opens the dashboard only; never triggers an audit automatically
REM    * reports startup failures instead of closing silently
REM
REM  Optional overrides (for testing / non-default setups):
REM    MRI_BAT_PORT=8057        use another port
REM    MRI_DASHBOARD_DB=path    serve a specific SQLite file
REM    MRI_BAT_NO_BROWSER=1     do not open the browser (CI/smoke checks)
REM ============================================================================

cd /d "%~dp0"

echo ===========================================
echo   MRI - AUTONOMOUS MARKETPLACE AUDITOR
echo   Integrated candidate (authenticated)
echo ===========================================
echo.

REM ---- 1. locate project + python -------------------------------------------
REM  Works both when the venv sits next to run.py (normal checkout) and when
REM  this .bat lives inside a git worktree whose venv is one level up.
set "VENV_PY="
if exist "%~dp0visibility_auditor_env\Scripts\python.exe" (
    set "VENV_PY=%~dp0visibility_auditor_env\Scripts\python.exe"
)
if not defined VENV_PY if exist "%~dp0..\visibility_auditor_env\Scripts\python.exe" (
    set "VENV_PY=%~dp0..\visibility_auditor_env\Scripts\python.exe"
)
if not defined VENV_PY (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined VENV_PY set "VENV_PY=%%P"
    )
)
if not defined VENV_PY (
    echo [ERROR] No se encontro Python ni el entorno virtual.
    echo         Buscado en:
    echo           "%~dp0visibility_auditor_env\Scripts\python.exe"
    echo           "%~dp0..\visibility_auditor_env\Scripts\python.exe"
    echo           PATH ^(python^)
    echo         Instale las dependencias con: pip install -r requirements.txt
    echo.
    if not defined MRI_BAT_NO_PAUSE pause
    exit /b 1
)
if not exist "%~dp0run.py" (
    echo [ERROR] No se encontro run.py en "%~dp0"
    if not defined MRI_BAT_NO_PAUSE pause
    exit /b 1
)
echo [1/5] Python  : "%VENV_PY%"
echo [1/5] Proyecto: "%~dp0"

REM ---- 2. TEMP/TMP BEFORE launching anything that may spawn Playwright ------
set "TEMP=%~dp0data\runtime_tmp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
if not exist "%TEMP%" (
    echo [ERROR] No se pudo crear el directorio temporal:
    echo         "%TEMP%"
    if not defined MRI_BAT_NO_PAUSE pause
    exit /b 1
)
echo [2/5] TEMP/TMP: "%TEMP%"

REM ---- 3. credentials are mandatory (MRI refuses to start unauthenticated) --
REM They may come from the caller's environment (the root launcher reads the
REM project .env) or from a .env next to this file; both are honoured.
if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
        if /i "%%A"=="DASHBOARD_USER" set "DASHBOARD_USER=%%B"
        if /i "%%A"=="DASHBOARD_PASS" set "DASHBOARD_PASS=%%B"
    )
)
if not defined DASHBOARD_USER goto :no_credentials
if not defined DASHBOARD_PASS goto :no_credentials
echo [3/5] Credenciales: usuario "%DASHBOARD_USER%" (cargado desde .env)

REM ---- 4. port / database ---------------------------------------------------
set "PORT=8055"
if defined MRI_BAT_PORT set "PORT=%MRI_BAT_PORT%"

set "DBARG="
if defined MRI_DASHBOARD_DB set "DBARG=--db "%MRI_DASHBOARD_DB%""
if defined MRI_DASHBOARD_DB (
    echo [4/5] SQLite: "%MRI_DASHBOARD_DB%"
) else (
    echo [4/5] SQLite: resolucion por defecto de MRI ^(no se fuerza ninguna ruta^)
)

REM refuse to start if the port is already taken (never steal a foreign service)
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] El puerto %PORT% ya esta en uso. Identifique el proceso con:
    echo         netstat -ano ^| findstr :%PORT%
    echo         y detengalo, o use MRI_BAT_PORT con otro puerto.
    if not defined MRI_BAT_NO_PAUSE pause
    exit /b 1
)

REM ---- smoke-test mode: run the server in THIS window (no browser, no waiting) --
REM Used to validate the launcher itself without opening a persistent window.
if defined MRI_BAT_FOREGROUND (
    echo [INFO] MRI_BAT_FOREGROUND: ejecutando el servidor en esta ventana...
    "%VENV_PY%" "%~dp0run.py" mri --port %PORT% %DBARG%
    set "RC=%ERRORLEVEL%"
    echo.
    echo [INFO] Servidor finalizado con codigo %RC%
    exit /b %RC%
)

echo [5/5] Iniciando servidor MRI en 127.0.0.1:%PORT% ...
echo.

REM Build a tiny helper script so the server invocation needs NO nested quoting
REM (nested quotes are the classic failure mode of `start ... cmd /k "..."`).
REM /k keeps the window open after exit, so a preflight/startup error stays
REM readable instead of vanishing together with the window.
set "SRV_SCRIPT=%TEMP%\mri_server_%PORT%.bat"
> "%SRV_SCRIPT%" echo @echo off
>>"%SRV_SCRIPT%" echo cd /d "%~dp0"
>>"%SRV_SCRIPT%" echo "%VENV_PY%" "%~dp0run.py" mri --port %PORT% %DBARG%
>>"%SRV_SCRIPT%" echo echo.
>>"%SRV_SCRIPT%" echo echo [MRI] servidor detenido. Puede cerrar esta ventana.
>>"%SRV_SCRIPT%" echo if not defined MRI_BAT_NO_PAUSE pause
start "MRI Server :%PORT%" cmd /k "%SRV_SCRIPT%"

REM ---- wait until the port actually accepts connections ---------------------
REM NOTE: `timeout /t 1` is unusable when stdin is redirected (it aborts
REM immediately), which made this loop exhaust its retries in milliseconds and
REM report a false "server did not start" while the server was still booting.
REM `ping -n 2` is a portable ~1s delay that works with or without a console.
set /a TRIES=0
:wait_server
ping -n 2 127.0.0.1 >nul 2>&1
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 goto :server_ready
set /a TRIES+=1
if %TRIES% GEQ 45 goto :server_timeout
goto :wait_server

:server_ready
echo.
echo ===========================================
echo   MRI activo en: http://127.0.0.1:%PORT%/
echo   Autenticacion: HTTP Basic (obligatoria)
echo.
echo   Use el usuario y la clave definidos en .env
echo   No se lanza ninguna auditoria automaticamente.
echo ===========================================
if defined MRI_BAT_NO_BROWSER (
    echo [INFO] MRI_BAT_NO_BROWSER definido: no se abre el navegador.
) else (
    start "" "http://127.0.0.1:%PORT%/"
)
echo.
echo Cierre la ventana "MRI Server" para detener el servicio.
endlocal
exit /b 0

:server_timeout
echo.
echo [ERROR] El servidor no comenzo a escuchar en %PORT% tras 45 segundos.
echo         Revise la ventana "MRI Server :%PORT%" para ver el error real.
if not defined MRI_BAT_NO_PAUSE pause
exit /b 1

:no_credentials
echo [ERROR] Faltan credenciales en "%~dp0.env".
echo         MRI exige autenticacion y no arrancara sin ellas.
echo.
echo         Cree el archivo .env junto a este .bat con:
echo             DASHBOARD_USER=su_usuario
echo             DASHBOARD_PASS=su_clave
echo.
echo         (Consulte .env.example para la plantilla.)
if not defined MRI_BAT_NO_PAUSE pause
exit /b 1

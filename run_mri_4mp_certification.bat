@echo off
setlocal

:: ========================================================
:: MRI 4MP AUTONOMOUS CERTIFICATION RUNNER
:: Orchestration script for the 4 marketplaces.
:: ========================================================

echo ========================================================
echo MRI 4MP AUTONOMOUS CERTIFICATION RUNNER
echo ========================================================
echo.

python _mri_4mp_certification_helper.py
set EXIT_CODE=%ERRORLEVEL%

echo.
echo ========================================================
echo RUNNER EXIT CODE: %EXIT_CODE%
echo ========================================================
pause
exit /b %EXIT_CODE%

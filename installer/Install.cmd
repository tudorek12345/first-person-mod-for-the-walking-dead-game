@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" %*
set "FP_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %FP_EXIT%

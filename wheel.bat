@echo off
cd /d "%~dp0"
if exist "%~dp0wheel.pyw" (
    start "" /b pythonw "%~dp0wheel.pyw"
) else (
    start "" /b python "%~dp0wheel.pyw"
)
exit /b

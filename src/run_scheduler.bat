@echo off
cd /d "%~dp0"
echo Building the V2.0 Executable...
pyinstaller --noconsole --onefile scheduler.py
echo.
echo Build complete! Your new .exe is in the 'dist' folder.
pause

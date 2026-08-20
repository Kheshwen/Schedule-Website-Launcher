cd /d "%~dp0"
echo Building the V2.0 Executable...
python -m PyInstaller --noconsole --onefile scheduler.py
echo Build complete! Your new .exe is in the 'dist' folder.
pause

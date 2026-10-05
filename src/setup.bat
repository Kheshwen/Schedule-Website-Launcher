cd /d "%~dp0"
<<<<<<< Updated upstream

echo Checking PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
)

echo Cleaning old build files...
rmdir /s /q build dist 2>nul
del /q "Website Launcher.spec" 2>nul

echo Building the V3.0 Executable...
python -m PyInstaller --noconsole --onefile --clean --icon icon.ico --name "Website Launcher" scheduler.py

if errorlevel 1 (
    echo.
    echo Build FAILED. Check the errors above.
) else (
    echo.
    echo Build complete! Your .exe is in the 'dist' folder.
)
pause
=======
echo Building the V2.0 Executable...
python -m PyInstaller --noconsole --onefile scheduler.py
echo Build complete! Your new .exe is in the 'dist' folder.
pause
>>>>>>> Stashed changes

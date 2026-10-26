@echo off
setlocal
echo === Schedule Website Launcher V3.3 - build ===

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller || goto :fail
)

echo Installing requirements...
python -m pip install --upgrade -r requirements.txt || goto :fail

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller --noconsole --onedir --clean --icon icon.ico --add-data "icon.ico;." --collect-data sv_ttk --collect-data tzdata --name "Website Launcher" scheduler.py || goto :fail

echo.
echo Done. The app is in dist\Website Launcher\
pause
exit /b 0

:fail
echo.
echo Build failed. See the messages above.
pause
exit /b 1

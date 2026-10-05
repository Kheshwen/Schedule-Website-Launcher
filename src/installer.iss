[Setup]
; DON'T CHANGE: unique ID for your app. Keep it the same across all versions
AppId={{8F3A6C2E-4B71-4D9A-9E15-27C0B5D1A834}
; OPTIONAL: the name shown in the installer and Start Menu
AppName=Website Launcher
; EDIT: change this every time you release a new version
AppVersion=3.0
; EDIT: replace with your name (e.g. Keshi)
AppPublisher=Your Name
; DON'T CHANGE: install location and Start Menu folder
DefaultDirName={autopf}\Website Launcher
DefaultGroupName=Website Launcher
; DON'T CHANGE: where the installer is saved
OutputDir=Output
; OPTIONAL: the installer's file name
OutputBaseFilename=WebsiteLauncher_Setup
; DON'T CHANGE: needs icon.ico in the same folder as this file
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Website Launcher.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; DON'T CHANGE: must match the --name in setup.bat ("Website Launcher")
Source: "dist\Website Launcher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Website Launcher"; Filename: "{app}\Website Launcher.exe"
Name: "{autodesktop}\Website Launcher"; Filename: "{app}\Website Launcher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Website Launcher.exe"; Description: "Launch Website Launcher"; Flags: nowait postinstall skipifsilent

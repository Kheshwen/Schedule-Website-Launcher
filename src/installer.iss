[Setup]

AppId={{8F3A6C2E-4B71-4D9A-9E15-27C0B5D1A834}
AppName=Website Launcher
AppVersion=3.0
AppPublisher=Keshi
DefaultDirName={autopf}\Website Launcher
DefaultGroupName=Website Launcher
OutputDir=Output
OutputBaseFilename=WebsiteLauncher_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Website Launcher.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\Website Launcher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Website Launcher"; Filename: "{app}\Website Launcher.exe"
Name: "{autodesktop}\Website Launcher"; Filename: "{app}\Website Launcher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Website Launcher.exe"; Description: "Launch Website Launcher"; Flags: nowait postinstall skipifsilent

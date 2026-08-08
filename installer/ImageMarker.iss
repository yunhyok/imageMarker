; ImageMarker Inno Setup Script
;
; Builds dist\ImageMarker-Setup-<version>.exe from the PyInstaller output
; at dist\ImageMarker.exe (build that first with build.bat).
;
; Compile with the repo-root build_installer.bat, or directly with:
;   ISCC.exe installer\ImageMarker.iss
;
; Requires Inno Setup 6: https://jrsoftware.org/isinfo.php

#define MyAppName "ImageMarker"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "yunhyok"
#define MyAppExeName "ImageMarker.exe"

[Setup]
; Fixed AppId - keep this stable across releases so Setup can detect and
; upgrade a previous install instead of creating a second one.
AppId={{F6C606C1-9595-4E99-A842-A954A79A7BC8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install by default (no admin prompt); Setup still shows a
; dialog letting the user opt into an all-users/admin install instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=ImageMarker-Setup-{#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\ImageMarker.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

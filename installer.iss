; installer.iss - Inno Setup Script (Unicode)
#define MyAppName "Kassensystem Basic"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Dein Unternehmen"
#define MyAppExeName "KassensystemBasic.exe"

; Wir installieren in einen SCHREIBBAREN Ordner (kein Admin nötig):
#define InstallDir "{localappdata}\Kassensystem Basic"

[Setup]
AppId={{2F1B6B7A-7D2B-4A2F-9B7C-5B1E0D7D4F11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={#InstallDir}
DefaultGroupName={#MyAppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=Kassensystem_Basic_Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
; HIER den Pfad zu deiner gebauten EXE anpassen:
Source: "dist\KassensystemBasic.exe"; DestDir: "{app}"; Flags: ignoreversion

; Falls du zusätzliche Ressourcen als lose Dateien brauchst (Logs/Icons etc.), hier ergänzen:
; Source: "extras\*"; DestDir: "{app}\extras"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName} starten"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung anlegen"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Kassensystem jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Optional: Benutzerdaten beim Deinstallieren stehen lassen (Standard sinnvoll).
; Wenn du auch Daten löschen willst, HIER gezielt aufräumen, z.B.:
; Type: filesandordirs; Name: "{app}\data"

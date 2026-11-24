; Inno-Setup-Skript für den Windows-Installer von djsync.
;
; Installiert pro Benutzer (ohne Adminrechte, ohne Code-Signierung) nach
; %LOCALAPPDATA%\Programs\djsync und legt einen Startmenü-Eintrag an.
; Konfiguration, Datenbank und Login liegen unabhängig davon unter %APPDATA%\djsync und werden
; vom Installer nicht angefasst – Daten einer früheren djsync.exe werden so weiterverwendet.
; Der Deinstaller fragt, ob %APPDATA%\djsync gelöscht werden soll.
;
; Voraussetzung: dist\djsync\ aus packaging\djsync.spec (PyInstaller).
; Aufruf (im Projektordner):
;   iscc /DAppVersion=0.3.0 packaging\djsync.iss
; Ergebnis: dist\djsync-setup-0.3.0.exe

#ifndef AppVersion
  #error AppVersion fehlt – Aufruf mit /DAppVersion=x.y.z
#endif

#define AppName "djsync"
#define AppExe "djsync.exe"
#define AppUrl "https://github.com/mhwso/djsync"

[Setup]
; Feste ID: Updates erkennen die bestehende Installation daran. Niemals ändern.
AppId={{6F0B8C1E-5D2A-4C47-9E3B-2A61D7F4C9B0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=mhwso
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases/latest
; Pro Benutzer, ohne Adminrechte: {autopf} wird zu %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DisableDirPage=auto
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=djsync-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Läuft djsync noch, bietet der Installer an, es zu schließen
CloseApplications=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\djsync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Laufzeitdateien einer früheren Version entfernen, damit keine veralteten Module liegen bleiben
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// Nach dem Deinstallieren: fragen, ob die Daten unter %APPDATA%\djsync gelöscht werden.
// Vorbelegt ist „Nein“, damit eine Neuinstallation die Einrichtung behält.
// Bei stiller Deinstallation (/SILENT, /VERYSILENT) bleiben die Daten immer erhalten.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  DataDir := ExpandConstant('{userappdata}\djsync');
  if not DirExists(DataDir) then
    Exit;
  if UninstallSilent then
    Exit;
  if MsgBox('Sollen auch deine djsync-Daten gelöscht werden?' + #13#10 + #13#10 +
            DataDir + #13#10 + #13#10 +
            'Dazu gehören Einstellungen, Spotify-Anmeldung und alle Zuordnungen und ' +
            'Review-Entscheidungen. Behalte sie, wenn du djsync später wieder installieren willst.',
            mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
  begin
    if not DelTree(DataDir, True, True, True) then
      MsgBox('Der Ordner konnte nicht vollständig gelöscht werden:' + #13#10 + DataDir,
             mbError, MB_OK);
  end;
end;

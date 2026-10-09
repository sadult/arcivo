; Inno Setup 6 script for Arcivo (per-user install, no admin rights required).
; Build:  iscc /DAppVersion=0.2.1 /DSourceDir=..\..\dist\Arcivo packaging\windows\arcivo.iss
#ifndef AppVersion
  #define AppVersion "0.2.1"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\Arcivo"
#endif
#define AppName "Arcivo"
#define AppPublisher "Bitologist"
#define AppURL "https://github.com/sadult/arcivo"
#define AppExe "Arcivo.exe"
#define DashExe "ArcivoDashboard.exe"
#define AumId "Bitologist.Arcivo.Dashboard"
#define Brand "..\..\src\arcivo\assets\brand"

[Setup]
AppId={{6F1C2E7A-5B8D-4C1E-9A3F-2D7B9E4A1C55}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\..\dist
OutputBaseFilename=Arcivo-{#AppVersion}-Setup-x64
SetupIconFile={#Brand}\installer.ico
UninstallDisplayIcon={app}\{#DashExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile={#Brand}\wizard-large.bmp
WizardSmallImageFile={#Brand}\wizard-small.bmp
Compression=lzma2/ultra64
SolidCompression=yes
LicenseFile=..\..\LICENSE
InfoBeforeFile=notice.txt
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} installer

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "clipath"; Description: "Add Arcivo to my PATH (use 'arcivo' commands in any terminal)"; GroupDescription: "Command line:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; "Arcivo" opens the console home screen (sign in, check connection, proxy, sync); "Arcivo Dashboard" opens the desktop app.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"; Comment: "Sign in, check the connection and manage Arcivo"
Name: "{autoprograms}\{#AppName} Dashboard"; Filename: "{app}\{#DashExe}"; AppUserModelID: "{#AumId}"; Comment: "Browse, search and export your Saved Messages"
Name: "{autoprograms}\{#AppName} Dashboard (demo data)"; Filename: "{app}\{#DashExe}"; Parameters: "--demo"; AppUserModelID: "{#AumId}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{autodesktop}\{#AppName} Dashboard"; Filename: "{app}\{#DashExe}"; Tasks: desktopicon; AppUserModelID: "{#AumId}"

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
  Tasks: clipath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open {#AppName} (sign in from the console home screen)"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; Program files only. User data (%APPDATA%\Arcivo, %LOCALAPPDATA%\Arcivo) and the stored session are kept unless
; the user chooses to remove them below.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Lowercase(Param) + ';', ';' + Lowercase(OrigPath) + ';') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('Also delete your local Arcivo data (index database, cache, logs and settings)?' + #13#10 +
              'Your Telegram account and messages are NOT affected. Choose No to keep the data for a later reinstall.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\Arcivo'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\Arcivo'), True, True, True);
      MsgBox('Local data removed. To also revoke the Telegram session, open Telegram > Settings > Devices and end the "Arcivo" session.',
             mbInformation, MB_OK);
    end;
  end;
end;

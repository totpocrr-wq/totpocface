; Inno Setup script for FaceSwap Studio
; Скачать Inno Setup: https://jrsoftware.org/isinfo.php
; Запуск:  ISCC.exe installer.iss
; Выход:   Output\FaceSwapStudio_Setup.exe

#define MyAppName "FaceSwap Studio"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Your Name"
#define MyAppExeName "FaceSwapStudio.exe"

[Setup]
AppId={{B3F4D2A5-9C8E-4A7B-B1E2-7F3D5C8A2E4F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FaceSwapStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=FaceSwapStudio_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
; Раскомментируй после того, как добавишь assets\app.ico
;SetupIconFile=assets\app.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
; Кладём всё содержимое dist\FaceSwapStudio
Source: "dist\FaceSwapStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

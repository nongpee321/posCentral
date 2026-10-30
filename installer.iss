[Setup]
AppName=PopCentral POS
AppVersion=1.9.4
DefaultDirName={autopf}\PopCentralPOS
DefaultGroupName=PopCentral POS
OutputBaseFilename=Setup_PopCentralPOS_v1.9.4
SetupIconFile=d:\pop-erp-food\python-pos\assets\icon.ico
Compression=none
SolidCompression=no
OutputDir=d:\pop-erp-food\python-pos\dist

[Files]
Source: "d:\pop-erp-food\python-pos\build\exe.win-amd64-3.14\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PopCentral POS"; Filename: "{app}\PopCentralPOS.exe"
Name: "{autodesktop}\PopCentral POS"; Filename: "{app}\PopCentralPOS.exe"

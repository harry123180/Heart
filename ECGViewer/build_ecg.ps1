$vsPath = "C:\Program Files\Microsoft Visual Studio\2022\Community"
$msvcVer = "14.44.35207"
$msvcBase = "$vsPath\VC\Tools\MSVC\$msvcVer"
$kitBase = "C:\Program Files (x86)\Windows Kits\10"
$kitVer = (Get-ChildItem "$kitBase\Include" | Sort-Object Name -Descending | Select-Object -First 1).Name

$env:Path = "$msvcBase\bin\HostX64\x64;$vsPath\Common7\IDE;$vsPath\Common7\Tools;$kitBase\bin\$kitVer\x64;" + $env:Path
$env:INCLUDE = "$msvcBase\include;$kitBase\Include\$kitVer\ucrt;$kitBase\Include\$kitVer\um;$kitBase\Include\$kitVer\shared;$kitBase\Include\$kitVer\winrt"
$env:LIB = "$msvcBase\lib\x64;$kitBase\Lib\$kitVer\ucrt\x64;$kitBase\Lib\$kitVer\um\x64"

& cmake --build "C:\Users\TSIC\Documents\GitHub\Heart\ECGViewer\build" --config Release
Write-Host "Build exit: $LASTEXITCODE"

# Setup MSVC environment manually
$vsPath = "C:\Program Files\Microsoft Visual Studio\2022\Community"
$msvcVer = "14.44.35207"
$msvcBase = "$vsPath\VC\Tools\MSVC\$msvcVer"
$kitBase = "C:\Program Files (x86)\Windows Kits\10"

# Find latest Windows Kit version
$kitVer = (Get-ChildItem "$kitBase\Include" | Sort-Object Name -Descending | Select-Object -First 1).Name

Write-Host "MSVC: $msvcVer"
Write-Host "WinKit: $kitVer"

# Set PATH (include Windows SDK bin for rc.exe, mt.exe)
$env:Path = "$msvcBase\bin\HostX64\x64;" +
            "$vsPath\Common7\IDE;" +
            "$vsPath\Common7\Tools;" +
            "$kitBase\bin\$kitVer\x64;" +
            $env:Path

# Set INCLUDE
$env:INCLUDE = "$msvcBase\include;" +
               "$kitBase\Include\$kitVer\ucrt;" +
               "$kitBase\Include\$kitVer\um;" +
               "$kitBase\Include\$kitVer\shared;" +
               "$kitBase\Include\$kitVer\winrt"

# Set LIB
$env:LIB = "$msvcBase\lib\x64;" +
           "$kitBase\Lib\$kitVer\ucrt\x64;" +
           "$kitBase\Lib\$kitVer\um\x64"

# Verify cl.exe
$cl = Get-Command cl.exe -ErrorAction SilentlyContinue
if (-not $cl) {
    Write-Error "cl.exe not found!"
    exit 1
}
Write-Host "Found: $($cl.Source)"

# Run CMake
$buildDir = "C:\Users\TSIC\Documents\GitHub\Heart\HelloQt\build"
$srcDir   = "C:\Users\TSIC\Documents\GitHub\Heart\HelloQt"
$qtPrefix = "C:\Users\TSIC\AppData\Local\anaconda3\Library"

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

& cmake -S $srcDir -B $buildDir `
    -G "NMake Makefiles" `
    -DCMAKE_PREFIX_PATH="$qtPrefix" `
    -DCMAKE_BUILD_TYPE=Release

Write-Host "CMake exit: $LASTEXITCODE"

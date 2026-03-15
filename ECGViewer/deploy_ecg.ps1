$exeDir    = "C:\Users\TSIC\Documents\GitHub\Heart\ECGViewer\build"
$deployDir = "C:\Users\TSIC\Documents\GitHub\Heart\ECGViewer\dist"
$qtBin     = "C:\Users\TSIC\AppData\Local\anaconda3\Library\bin"
$wdq       = "$qtBin\windeployqt.exe"

# 建立 dist 資料夾並複製 exe
New-Item -ItemType Directory -Force -Path $deployDir | Out-Null
Copy-Item "$exeDir\ECGViewer.exe" "$deployDir\" -Force
Write-Host "Copied ECGViewer.exe to $deployDir"

# 執行 windeployqt — 自動複製所有需要的 Qt DLL
$env:Path = "$qtBin;" + $env:Path
& $wdq --release --no-translations --no-system-d3d-compiler --no-opengl-sw "$deployDir\ECGViewer.exe"
Write-Host "windeployqt exit: $LASTEXITCODE"

if ($LASTEXITCODE -eq 0) {
    $files = (Get-ChildItem $deployDir).Count
    Write-Host "Done. $files files in $deployDir"
    Write-Host "You can now double-click: $deployDir\ECGViewer.exe"
}

$exeDir    = "C:\Users\TSIC\Documents\GitHub\Heart\ECGViewer\build"
$deployDir = "C:\Users\TSIC\Documents\GitHub\Heart\ECGViewer\dist"
$qtBin     = "C:\Users\TSIC\AppData\Local\anaconda3\Library\bin"
$wdq       = "$qtBin\windeployqt.exe"
$dumpbin   = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\HostX64\x64\dumpbin.exe"

# --- Recursive DLL dependency scanner ---
function Get-AllDependencies {
    param([string]$startExe, [string]$outDir, [string[]]$searchPaths)

    $sysDirs = @(
        "$env:SystemRoot\System32",
        "$env:SystemRoot\SysWOW64",
        "$env:SystemRoot\WinSxS"
    )
    $visited = [System.Collections.Generic.HashSet[string]]::new(
                   [System.StringComparer]::OrdinalIgnoreCase)
    $queue   = [System.Collections.Generic.Queue[string]]::new()

    $queue.Enqueue($startExe)
    $visited.Add([IO.Path]::GetFileName($startExe)) | Out-Null

    # Seed with DLLs already copied by windeployqt (including plugins subdir)
    Get-ChildItem $outDir -Filter "*.dll" -Recurse | ForEach-Object {
        if ($visited.Add($_.Name)) { $queue.Enqueue($_.FullName) }
    }

    while ($queue.Count -gt 0) {
        $cur = $queue.Dequeue()
        if (-not (Test-Path $cur)) { continue }

        $deps = & $dumpbin /dependents $cur 2>$null |
                Where-Object { $_ -match "^\s+\S+\.dll\s*$" } |
                ForEach-Object { $_.Trim() }

        foreach ($dep in $deps) {
            if (-not $visited.Add($dep)) { continue }

            # Skip system DLLs
            if ($sysDirs | Where-Object { Test-Path "$_\$dep" }) { continue }

            # Already in dist -- just recurse into it
            $inDist = "$outDir\$dep"
            if (Test-Path $inDist) { $queue.Enqueue($inDist); continue }

            # Search and copy
            $found = $false
            foreach ($sp in $searchPaths) {
                $candidate = "$sp\$dep"
                if (Test-Path $candidate) {
                    Copy-Item $candidate "$outDir\" -Force
                    Write-Host "  + $dep"
                    $queue.Enqueue("$outDir\$dep")
                    $found = $true; break
                }
            }
            if (-not $found) { Write-Warning "  ? NOT FOUND: $dep" }
        }
    }
}

# --- Main ---
New-Item -ItemType Directory -Force -Path $deployDir | Out-Null
Copy-Item "$exeDir\ECGViewer.exe" "$deployDir\" -Force
Write-Host "Copied ECGViewer.exe"

# Step 1: windeployqt
$env:Path = "$qtBin;" + $env:Path
& $wdq --release --no-translations --no-system-d3d-compiler --no-opengl-sw "$deployDir\ECGViewer.exe"
Write-Host "windeployqt: $LASTEXITCODE"

# Step 2: recursive scan for remaining dependencies
$msvcVer = (Get-ChildItem "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Redist\MSVC" |
            Sort-Object Name -Descending | Select-Object -First 1).Name
$crtDir  = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Redist\MSVC\$msvcVer\x64\Microsoft.VC143.CRT"

Write-Host "`nScanning all DLL dependencies recursively..."
Get-AllDependencies "$deployDir\ECGViewer.exe" $deployDir @($qtBin, $crtDir)

$files = (Get-ChildItem $deployDir -Recurse -File).Count
Write-Host "`nDone. $files files in $deployDir"

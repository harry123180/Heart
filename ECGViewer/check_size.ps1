$dir = "C:\Users\TSIC\Documents\GitHub\Heart\ECGViewer\dist"
$items = Get-ChildItem $dir -Recurse -File
$total = ($items | Measure-Object -Property Length -Sum).Sum
Write-Host ("Total: {0:F1} MB ({1} files)" -f ($total/1MB), $items.Count)
Write-Host ""
$items | Sort-Object Length -Descending | ForEach-Object {
    Write-Host ("{0,-40} {1,6:F1} MB" -f $_.Name, ($_.Length/1MB))
}

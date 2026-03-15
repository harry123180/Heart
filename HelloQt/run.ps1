# Add Qt DLLs to PATH so the exe can find them
$env:Path = "C:\Users\TSIC\AppData\Local\anaconda3\Library\bin;" + $env:Path

Start-Process "C:\Users\TSIC\Documents\GitHub\Heart\HelloQt\build\HelloQt.exe"

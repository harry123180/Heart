@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > nul 2>&1
cmake -S "C:\Users\TSIC\Documents\GitHub\Heart\HelloQt" -B "C:\Users\TSIC\Documents\GitHub\Heart\HelloQt\build" -G "NMake Makefiles" -DCMAKE_PREFIX_PATH="C:\Users\TSIC\AppData\Local\anaconda3\Library" -DCMAKE_BUILD_TYPE=Release > "C:\Users\TSIC\Documents\GitHub\Heart\HelloQt\cmake_out.txt" 2>&1
echo cmake exit code: %ERRORLEVEL%

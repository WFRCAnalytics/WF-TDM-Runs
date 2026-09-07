@echo off

rem Set the name of the Python script
set script=_start-server-static.py

rem Prefer the real Python launcher (py.exe) over "python", which on some
rem machines resolves to the Windows Store app-execution-alias stub instead
rem of a real interpreter.
where py >nul 2>nul
if %errorlevel%==0 (
    start /b py %script%
    goto :eof
)

rem Find the Python executable in the PATH
for /f %%i in ('where python') do set python_exec=%%i

rem Check if Python executable was found
if not defined python_exec (
    echo Python executable not found in PATH.
    pause
    exit /b 1
)

rem Start the Python script using the found Python executable
start /b %python_exec% %script%
@echo off
REM Quick commit script with timestamp
REM Adds all changes, commits with epoch seconds as message, and pushes to origin

echo Adding all changes...
git add .

REM Get current timestamp in seconds since epoch
for /f "tokens=*" %%i in ('powershell -command "[int64](([datetime]::UtcNow)-([datetime]'1970-01-01')).TotalSeconds"') do set TIMESTAMP=%%i

echo Creating commit with timestamp: %TIMESTAMP%
git commit -m "%TIMESTAMP%"

if %errorlevel% neq 0 (
    echo No changes to commit or commit failed
    pause
    exit /b 1
)

echo Pushing to origin...
git push

if %errorlevel% neq 0 (
    echo Push failed
    pause
    exit /b 1
)

echo Successfully committed and pushed with message: %TIMESTAMP%
pause
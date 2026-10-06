@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem First run only: ask for the Last.fm API key and remember it in a file called .env
if not exist .env (
    echo First run: paste your free Last.fm API key ^(from https://www.last.fm/api^)
    set /p KEY=Key: 
    >.env echo LASTFM_API_KEY=!KEY!
)

echo Collecting today's charts...
python collect.py
if errorlevel 1 echo Could not update the charts, so the page will use the data already saved.

echo Building the page...
python build.py
if errorlevel 1 goto failed

start "" "site\index.html"
exit /b 0

:failed
echo.
echo Something went wrong. Read the message above.
pause
exit /b 1

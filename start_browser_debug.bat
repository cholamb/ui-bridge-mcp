@echo off
chcp 65001 >nul
setlocal
echo.
echo  UiBridge - starting a browser in CDP debug mode (port 9222)...
echo.

:: Chrome first, then Edge
set "BROWSER="
for %%P in (
  "C:\Program Files\Google\Chrome\Application\chrome.exe"
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) do if exist %%P if not defined BROWSER set "BROWSER=%%~P"

if not defined BROWSER (
  echo  [ERROR] Chrome / Edge not found. Install one, then rerun.
  pause
  exit /b 1
)

:: Isolated profile so this NEVER collides with a normal browser window that's
:: already open. That collision is the #1 reason plain --remote-debugging-port
:: silently fails (Chrome forwards the flag to the existing instance, no port
:: opens). Log into your sites in THIS window; the profile persists.
set "PROFILE=%LOCALAPPDATA%\ui-bridge-browser-9222"

start "" "%BROWSER%" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check

echo  [OK] Debug browser launched.
echo       - CDP endpoint : http://localhost:9222
echo       - Profile      : %PROFILE%
echo       - Log into sites in THIS window; ui-bridge web_* tools can now connect.
echo.
timeout /t 3 >nul
endlocal

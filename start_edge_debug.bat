@echo off
chcp 65001 >nul
echo Edge 디버그 모드로 실행 중... (CDP 포트: 9222)

:: Edge 경로 자동 탐색
set "EDGE_PATH="
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    set "EDGE_PATH=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)
if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
    set "EDGE_PATH=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)

if "%EDGE_PATH%"=="" (
    echo Edge를 찾을 수 없습니다. Chrome으로 시도합니다...
    if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
        set "EDGE_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
    )
    if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
        set "EDGE_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )
)

if "%EDGE_PATH%"=="" (
    echo 브라우저를 찾을 수 없습니다.
    pause
    exit /b 1
)

start "" "%EDGE_PATH%" --remote-debugging-port=9222 --remote-allow-origins=*
echo 브라우저가 디버그 모드로 실행되었습니다.
timeout /t 2 >nul

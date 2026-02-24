@echo off
chcp 65001 >nul
echo 正在備份專案...
for /f "usebackq tokens=*" %%a in (`powershell -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"`) do set stamp=%%a
set "DEST=backup\backup_%stamp%"
mkdir "%DEST%" 2>nul
robocopy . "%DEST%" /E /XD backup __pycache__ .git .venv .pytest_cache /XF backup.bat
echo 備份完成！儲存於 %DEST%

@echo off
echo ========================================
echo   포도알 크롤러 EXE 빌드
echo ========================================
echo.

:: PyInstaller 설치 확인
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller 설치 중...
    pip install pyinstaller
)

echo.
echo EXE 빌드 시작...
echo.

pyinstaller --onefile --windowed --name "포도알크롤러" --icon=NONE crawrling_ui.py

echo.
echo ========================================
echo   빌드 완료!
echo   dist 폴더에서 "포도알크롤러.exe" 확인
echo ========================================
pause

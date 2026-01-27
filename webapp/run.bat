@echo off
echo ========================================
echo   포도알 크롤러 웹앱 시작
echo ========================================
echo.

pip install -r requirements.txt -q

echo 서버 시작 중...
echo http://localhost:5000 에서 접속하세요
echo.

python app.py
pause

# Python + Chrome for Selenium
FROM python:3.11-slim

# Chrome 설치 (새로운 방식)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ChromeDriver 설치
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d'.' -f1-3) \
    && wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}.0/linux64/chromedriver-linux64.zip" -O /tmp/chromedriver.zip \
    || wget -q "https://storage.googleapis.com/chrome-for-testing-public/$(curl -s https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE)/linux64/chromedriver-linux64.zip" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver*

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 복사
COPY . .

# 다운로드 폴더 생성
RUN mkdir -p downloads

# 포트 설정
EXPOSE 5000

# 실행
CMD ["gunicorn", "--worker-class", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", "--bind", "0.0.0.0:5000", "--timeout", "300", "app:app"]

# GitHub Actions 포도알 자동화 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 포도알 스케줄 크롤러를 GitHub Actions로 자동화하여 크롤링 → Import → 티켓오픈 처리 → 이메일 발송까지 전체 워크플로우를 자동 수행한다.

**Architecture:** 단일 Python 스크립트(`automate.py`)가 Selenium으로 전체 플로우를 순차 실행. GitHub Actions가 cron 스케줄 또는 수동 트리거로 이 스크립트를 호출. 환경변수로 자격증명 전달.

**Tech Stack:** Python 3.11, Selenium 4, Pandas, GitHub Actions, Chrome headless

**Spec:** `docs/superpowers/specs/2026-03-15-github-actions-automation-design.md`

---

## Chunk 1: automate.py 핵심 스크립트

### Task 1: automate.py 기본 구조 및 크롤링 함수

**Files:**
- Create: `automate.py`

- [ ] **Step 1: automate.py 파일 생성 - 설정, 유틸리티, 크롤링 함수**

기존 `crawrling.py`의 크롤링 로직을 재사용하되, 환경변수 기반으로 변경. 핵심 내용:

```python
import os
import time
import re
import smtplib
import sys
import pandas as pd
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# 환경변수에서 설정 로드
PODOAL_ID = os.environ["PODOAL_ID"]
PODOAL_PW = os.environ["PODOAL_PW"]
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
SENDER_PASSWORD = os.environ["SENDER_PASSWORD"]
RECEIVER_EMAIL = os.environ["RECEIVER_EMAIL"]
MYUKIT_URL = "https://myukit.com/"

CONFIG = {
    "musical": {
        "base_url": "https://podor.co.kr/admin/performance",
        "open_path": "/performance_open/",
        "schedule_path": "/performanceschedule/",
        "season_path": "/performance_season/",
        "place_url": "https://podor.co.kr/admin/performance/performance_place/",
        "prefix": "musical"
    },
    "play": {
        "base_url": "https://podor.co.kr/admin/plays",
        "open_path": "/play_open/",
        "schedule_path": "/playschedule/",
        "season_path": "/play_season/",
        "place_url": "https://podor.co.kr/admin/performance/performance_place/",
        "prefix": "play"
    }
}
```

유틸리티 함수(`parse_date`, `setup_driver`)는 `crawrling.py` 기반으로 작성.

`setup_driver()`는 GitHub Actions 환경에 맞게:
```python
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(options=options)
```

`run_scrape(driver, category)` - `crawrling.py:100-223`의 로직을 그대로 가져오되 `input()` 제거. 반환값: Excel 파일 경로 또는 None.

- [ ] **Step 2: 로컬에서 크롤링 함수만 테스트 실행**

```bash
PODOAL_ID=podor PODOAL_PW=... python -c "
from automate import setup_driver, run_scrape
driver = setup_driver()
driver.get('https://podor.co.kr/admin/login/')
# 로그인 후 run_scrape 호출 확인
driver.quit()
"
```

- [ ] **Step 3: Commit**

```bash
git add automate.py
git commit -m "feat: add automate.py with crawling function"
```

---

### Task 2: Import 함수 추가

**Files:**
- Modify: `automate.py`

- [ ] **Step 1: run_import 함수 작성**

`automate.py`에 추가. Import 페이지 URL은 카테고리별로 다름:
- musical: `https://podor.co.kr/admin/performance/performanceschedule/import/`
- play: `https://podor.co.kr/admin/plays/playschedule/import/`

```python
def run_import(driver, category, file_path):
    """Excel 파일을 포도알에 Import"""
    conf = CONFIG[category]
    wait = WebDriverWait(driver, 15)

    import_url = f"{conf['base_url']}{conf['schedule_path']}import/"
    print(f"📤 Import 시작: {import_url}")
    driver.get(import_url)
    time.sleep(2)

    # 파일 업로드
    file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
    file_input.send_keys(os.path.abspath(file_path))
    print(f"   -> 파일 선택: {os.path.basename(file_path)}")

    # Format 드롭다운에서 xlsx 선택
    format_select = Select(driver.find_element(By.NAME, "format"))
    format_select.select_by_visible_text("xlsx")
    time.sleep(1)

    # Submit
    submit_btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
    submit_btn.click()
    time.sleep(3)
    print("   -> Submit 완료")

    # Confirm Import
    confirm_btn = wait.until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, "input[type='submit'][value='Confirm import']")
    ))
    confirm_btn.click()
    time.sleep(3)
    print("   -> Confirm Import 완료!")
```

Format 드롭다운의 정확한 텍스트값이 "xlsx"가 아닐 수 있음 - 실행 시 확인 필요. `select_by_value`로 fallback.

- [ ] **Step 2: Commit**

```bash
git add automate.py
git commit -m "feat: add import function to automate.py"
```

---

### Task 3: 티켓오픈 처리 함수 추가

**Files:**
- Modify: `automate.py`

- [ ] **Step 1: handle_ticket_open 함수 작성**

핵심 로직:
1. 티켓오픈 페이지 이동
2. 각 행에서 오픈날짜 확인
3. 오늘 기준 **엄격히 과거**(오늘 미포함)인 항목 → 체크박스 선택
4. 오늘 이후(오늘 포함)인 항목 → 상세 페이지 진입 → 스케줄반영 입력 → Save
5. 삭제 대상 일괄 삭제

```python
def handle_ticket_open(driver, category):
    """티켓오픈 처리: 지난 항목 삭제, 미래 항목 반영완료 표시"""
    conf = CONFIG[category]
    wait = WebDriverWait(driver, 15)
    today = date.today()

    open_url = f"{conf['base_url']}{conf['open_path']}"
    print(f"🎫 티켓오픈 처리 시작: {open_url}")
    driver.get(open_url)
    time.sleep(2)

    rows = driver.find_elements(By.CSS_SELECTOR, "#result_list tbody tr")
    if not rows:
        print("   -> 티켓오픈 항목 없음")
        return {"deleted": 0, "updated": 0}

    deleted_count = 0
    updated_count = 0
    items_to_delete = []  # 체크박스 value 저장
    items_to_update = []  # (공연명 링크 URL, 공연명) 저장

    for row in rows:
        cells = row.find_elements(By.CSS_SELECTOR, "td, th")
        # 4번 스크린샷 기준: 공연명(1), 시즌id(2), 오픈날짜(3), 오픈시간(4), 스케줄반영(5)
        if len(cells) < 5:
            continue

        open_date_str = cells[3].text.strip()  # 오픈날짜 컬럼
        schedule_status = cells[5].text.strip()  # 스케줄반영 컬럼

        try:
            open_date = datetime.strptime(open_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        checkbox = row.find_element(By.CSS_SELECTOR, "input.action-select")
        checkbox_value = checkbox.get_attribute("value")

        if open_date < today:
            # 오늘 이전 → 삭제 대상
            items_to_delete.append(checkbox_value)
        elif schedule_status != "반영 완료":
            # 오늘 이후 + 아직 반영 안 됨 → 반영완료 표시 대상
            link = cells[1].find_element(By.TAG_NAME, "a")
            items_to_update.append((link.get_attribute("href"), cells[1].text.strip()))

    # 1) 반영완료 처리 (먼저 처리 - 삭제하면 페이지가 변경되므로)
    for url, name in items_to_update:
        print(f"   -> '{name}' 반영완료 처리 중...")
        driver.get(url)
        time.sleep(1)

        field = driver.find_element(By.ID, "id_스케줄반영")
        field.clear()
        field.send_keys("반영 완료")

        save_btn = driver.find_element(By.CSS_SELECTOR, "input[name='_save']")
        save_btn.click()
        time.sleep(2)
        updated_count += 1

    # 2) 지난 항목 삭제
    if items_to_delete:
        driver.get(open_url)
        time.sleep(2)

        for value in items_to_delete:
            checkbox = driver.find_element(
                By.CSS_SELECTOR, f"input.action-select[value='{value}']"
            )
            checkbox.click()

        # Delete 액션 선택
        action_select = Select(driver.find_element(By.NAME, "action"))
        action_select.select_by_value("delete_selected")

        # Go 버튼 클릭
        go_btn = driver.find_element(By.CSS_SELECTOR, "button[name='index']")
        go_btn.click()
        time.sleep(2)

        # "Yes, I'm sure" 확인
        confirm_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[value=\"Yes, I'm sure\"]")
        ))
        confirm_btn.click()
        time.sleep(2)
        deleted_count = len(items_to_delete)
        print(f"   -> {deleted_count}개 삭제 완료")

    print(f"   -> 처리 완료: 삭제 {deleted_count}건, 반영완료 {updated_count}건")
    return {"deleted": deleted_count, "updated": updated_count}
```

**안전장치:** `open_date < today` (엄격히 과거만). 오늘 항목은 삭제하지 않음.

- [ ] **Step 2: Commit**

```bash
git add automate.py
git commit -m "feat: add ticket open handling to automate.py"
```

---

### Task 4: 이메일 발송 및 메인 함수

**Files:**
- Modify: `automate.py`

- [ ] **Step 1: send_result_email 함수 작성**

```python
def send_result_email(category, file_path, scrape_count, ticket_result, error=None):
    """결과 이메일 발송"""
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL

    if error:
        msg['Subject'] = f"[포도알 자동화] ❌ {category.upper()} 오류 - {datetime.now().strftime('%m/%d')}"
        body = f"오류 발생:\n{error}"
    else:
        msg['Subject'] = f"[포도알 자동화] ✅ {category.upper()} 완료 - {datetime.now().strftime('%m/%d')}"
        body = f"""포도알 {category.upper()} 자동화 결과

■ 크롤링: {scrape_count}개 신규 스케줄
■ 티켓오픈: 삭제 {ticket_result['deleted']}건, 반영완료 {ticket_result['updated']}건
■ Import: {'완료' if scrape_count > 0 else '스킵 (신규 없음)'}
"""

    msg.attach(MIMEText(body, 'plain'))

    # Excel 첨부
    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file_path)}")
            msg.attach(part)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("📧 이메일 발송 완료")
```

- [ ] **Step 2: main 함수 작성**

```python
def main():
    category = sys.argv[1] if len(sys.argv) > 1 else "musical"
    if category not in CONFIG:
        print(f"❌ 잘못된 카테고리: {category}")
        sys.exit(1)

    print(f"{'='*50}")
    print(f"포도알 자동화 시작: {category.upper()}")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    driver = None
    file_path = None
    scrape_count = 0
    ticket_result = {"deleted": 0, "updated": 0}

    try:
        driver = setup_driver()

        # 1. 로그인
        print("\n🔐 포도알 로그인...")
        driver.get("https://podor.co.kr/admin/login/")
        driver.find_element(By.NAME, "username").send_keys(PODOAL_ID)
        driver.find_element(By.NAME, "password").send_keys(PODOAL_PW + Keys.ENTER)
        time.sleep(2)
        print("   -> 로그인 완료")

        # 2. 크롤링
        file_path = run_scrape(driver, category)
        if file_path:
            scrape_count = len(pd.read_excel(file_path))
            print(f"\n✅ {scrape_count}개 스케줄 저장: {file_path}")

            # 3. Import
            run_import(driver, category, file_path)
        else:
            print("\n📭 신규 스케줄 없음 - Import 스킵")

        # 4. 티켓오픈 처리
        ticket_result = handle_ticket_open(driver, category)

        # 5. 이메일 발송
        send_result_email(category, file_path, scrape_count, ticket_result)

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        # 스크린샷 저장
        if driver:
            driver.save_screenshot("error_screenshot.png")
        try:
            send_result_email(category, file_path, scrape_count, ticket_result, error=str(e))
        except:
            print("이메일 발송도 실패")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add automate.py
git commit -m "feat: add email and main function to automate.py"
```

---

## Chunk 2: GitHub Actions 워크플로우

### Task 5: 뮤지컬 워크플로우

**Files:**
- Create: `.github/workflows/podoal-musical.yml`

- [ ] **Step 1: 워크플로우 파일 작성**

```yaml
name: 포도알 뮤지컬 자동화

on:
  schedule:
    # 월,수,토 KST 04:00 = UTC 전날 19:00
    # cron: 일(0) 월(1) 화(2) 수(3) 목(4) 금(5) 토(6)
    # 월(1),수(3),토(6) KST → 일(0),화(2),금(5) UTC
    - cron: '0 19 * * 0,2,5'
  workflow_dispatch:
    inputs:
      category:
        description: '카테고리'
        required: true
        default: 'musical'
        type: choice
        options:
          - musical

jobs:
  automate:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Chrome
        uses: browser-actions/setup-chrome@v1
        with:
          chrome-version: stable

      - name: Install dependencies
        run: |
          pip install selenium pandas openpyxl webdriver-manager

      - name: Run automation
        env:
          PODOAL_ID: ${{ secrets.PODOAL_ID }}
          PODOAL_PW: ${{ secrets.PODOAL_PW }}
          SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
          SENDER_PASSWORD: ${{ secrets.SENDER_PASSWORD }}
          RECEIVER_EMAIL: ${{ secrets.RECEIVER_EMAIL }}
        run: python automate.py musical

      - name: Upload error screenshot
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: error-screenshot
          path: error_screenshot.png
          retention-days: 7
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/podoal-musical.yml
git commit -m "feat: add GitHub Actions workflow for musical"
```

---

### Task 6: 연극 워크플로우

**Files:**
- Create: `.github/workflows/podoal-play.yml`

- [ ] **Step 1: 워크플로우 파일 작성**

뮤지컬 워크플로우와 동일한 구조, 스케줄과 카테고리만 변경:

```yaml
name: 포도알 연극 자동화

on:
  schedule:
    # 화,목,일 KST 04:00 = UTC 전날 19:00
    # 화(2),목(4),일(0) KST → 월(1),수(3),토(6) UTC
    - cron: '0 19 * * 1,3,6'
  workflow_dispatch:
    inputs:
      category:
        description: '카테고리'
        required: true
        default: 'play'
        type: choice
        options:
          - play

jobs:
  automate:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Chrome
        uses: browser-actions/setup-chrome@v1
        with:
          chrome-version: stable

      - name: Install dependencies
        run: |
          pip install selenium pandas openpyxl webdriver-manager

      - name: Run automation
        env:
          PODOAL_ID: ${{ secrets.PODOAL_ID }}
          PODOAL_PW: ${{ secrets.PODOAL_PW }}
          SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
          SENDER_PASSWORD: ${{ secrets.SENDER_PASSWORD }}
          RECEIVER_EMAIL: ${{ secrets.RECEIVER_EMAIL }}
        run: python automate.py play

      - name: Upload error screenshot
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: error-screenshot
          path: error_screenshot.png
          retention-days: 7
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/podoal-play.yml
git commit -m "feat: add GitHub Actions workflow for play"
```

---

### Task 7: GitHub Secrets 설정 안내 및 최종 확인

- [ ] **Step 1: GitHub Secrets 설정**

GitHub 리포지토리 Settings → Secrets and variables → Actions에서 5개 Secret 추가:
- `PODOAL_ID`
- `PODOAL_PW`
- `SENDER_EMAIL`
- `SENDER_PASSWORD`
- `RECEIVER_EMAIL`

- [ ] **Step 2: 수동 트리거로 테스트**

GitHub Actions 탭 → "포도알 뮤지컬 자동화" → "Run workflow" → 실행 확인

- [ ] **Step 3: 최종 Commit (전체 확인 후)**

```bash
git add -A
git commit -m "feat: complete GitHub Actions automation for podoal crawler"
git push
```

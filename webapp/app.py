import os
import time
import re
import threading
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_socketio import SocketIO, emit
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)
app.secret_key = 'podoal_secret_key_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# 작업 상태 저장
tasks = {}

# ==========================================
# 설정
# ==========================================
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
MYUKIT_URL = "https://myukit.com/"

# 티켓 필드
TICKET_FIELDS = [
    ("인터파크", "인터파크주소"),
    ("멜론티켓", "멜론티켓주소"),
    ("예스24", "예스24주소"),
    ("티켓링크", "티켓링크주소"),
    ("총무", "총무주소"),
    ("샬롯", "샬롯주소"),
    ("예술의전당", "예술의전당주소"),
    ("세종", "세종주소"),
    ("국립극장", "국립극장주소"),
    ("부산드림씨어터", "부산드림씨어터주소"),
    ("성남아트센터", "성남아트센터주소"),
    ("KT G", "kT_G주소"),
    ("LG아트센터", "LG아트센터주소"),
]

# ==========================================
# 유틸리티
# ==========================================
def parse_ids(id_string):
    ids = []
    if not id_string: return ids
    parts = [p.strip() for p in id_string.replace(' ', '').split(',')]
    for part in parts:
        if '~' in part:
            try:
                start, end = part.split('~')
                ids.extend(range(int(start), int(end) + 1))
            except: pass
        else:
            try: ids.append(int(part))
            except: pass
    return ids

def parse_date(date_str):
    if not date_str or date_str.strip() in ["-", ""]: return datetime(2000, 1, 1)
    clean_str = date_str.strip().replace(",", "").replace(".", "")
    clean_str = re.sub(r'\(.*?\)', '', clean_str).strip()
    formats = ["%Y-%m-%d", "%b %d %Y", "%B %d %Y"]
    for fmt in formats:
        try: return datetime.strptime(clean_str, fmt)
        except: continue
    return datetime(2000, 1, 1)

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# ==========================================
# 크롤링 로직
# ==========================================
def run_crawl_task(task_id, username, password, category, filter_ids):
    """백그라운드 크롤링 작업"""
    task = tasks[task_id]
    task['status'] = 'running'
    task['logs'] = []

    def log(msg):
        task['logs'].append(msg)
        socketio.emit('log', {'task_id': task_id, 'message': msg})

    driver = None
    try:
        log(f"🚀 {category.upper()} 크롤링 시작...")
        driver = setup_driver()

        # 로그인
        log("🔐 포도알 로그인 중...")
        driver.get("https://podor.co.kr/admin/login/")
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password + Keys.ENTER)
        time.sleep(2)
        log("✅ 로그인 완료")

        conf = CONFIG[category]
        wait = WebDriverWait(driver, 15)
        category_data = []

        # ID 추출
        driver.get(f"{conf['base_url']}{conf['schedule_path']}")
        time.sleep(3)
        first_row = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result_list tbody tr:first-child")))
        first_id = int(first_row.find_element(By.CSS_SELECTOR, "th.field-id, td.field-id").text.strip())
        current_id = first_id + 1
        log(f"   -> 시작 ID: {current_id}")

        # 티켓오픈 대상 수집
        driver.get(f"{conf['base_url']}{conf['open_path']}")
        rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#result_list tbody tr")))
        targets = []
        for row in rows:
            cells = row.find_elements(By.CSS_SELECTOR, "td, th")
            if len(cells) >= 6 and cells[5].text.strip() == "-":
                season_id = cells[2].text.strip()
                if filter_ids and int(season_id) not in filter_ids:
                    continue
                targets.append({"title": cells[1].text.strip(), "season_id": season_id})

        log(f"   -> 대상 공연 수: {len(targets)}")

        for idx, target in enumerate(targets):
            perf_name = target['title']
            log(f"🔍 [{idx+1}/{len(targets)}] '{perf_name}' 분석 중...")

            try:
                # 공연장 ID
                driver.get(f"{conf['base_url']}{conf['season_path']}?q={target['season_id']}")
                s_row = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result_list tbody tr:first-child")))
                place_name = s_row.find_elements(By.TAG_NAME, "td")[4].text.strip()

                driver.get(f"{conf['place_url']}?q={place_name}")
                place_id = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "th.field-id, td.field-id"))).text.strip()

                # 최신 날짜
                driver.get(f"{conf['base_url']}{conf['schedule_path']}?q={perf_name}&o=-2")
                max_date = datetime(2000, 1, 1)
                try:
                    sc_rows = WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#result_list tbody tr")))
                    for sc_row in sc_rows:
                        for td in sc_row.find_elements(By.TAG_NAME, "td"):
                            td_text = td.text.strip()
                            parsed = None
                            if re.match(r'^\d{4}-\d{2}-\d{2}$', td_text):
                                parsed = datetime.strptime(td_text, "%Y-%m-%d")
                            elif re.match(r'^[A-Za-z]+\.\s*\d{1,2},\s*\d{4}$', td_text):
                                try:
                                    parsed = datetime.strptime(td_text.replace(".", ""), "%b %d, %Y")
                                except: pass
                            elif re.match(r'^[A-Za-z]+ \d{1,2}, \d{4}$', td_text):
                                try:
                                    parsed = datetime.strptime(td_text, "%B %d, %Y")
                                except: pass
                            if parsed and parsed > max_date:
                                max_date = parsed
                    if max_date > datetime(2000, 1, 1):
                        log(f"   -> 최신 날짜: {max_date.strftime('%Y-%m-%d')}")
                except: pass

                # 뮤킷 검색
                driver.get(MYUKIT_URL)
                search = wait.until(EC.presence_of_element_located((By.ID, "sch-v1-input")))
                search.clear()
                search.send_keys(re.sub(r'\[.*?\]', '', perf_name).strip())
                try:
                    res = WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.ID, "sch-v1-results")))
                    items = res.find_elements(By.TAG_NAME, "li")
                    clicked = False
                    for i in items:
                        if "진행 중" in i.text: i.click(); clicked = True; break
                    if not clicked: items[0].click()
                    time.sleep(2)
                    driver.find_element(By.ID, "show-list-btn").click()
                    time.sleep(2)
                except:
                    log(f"   ⏩ 뮤킷 데이터 없음 (스킵)")
                    continue

                # 데이터 수집
                mu_rows = driver.find_elements(By.CSS_SELECTOR, ".actor-schedule-list-table tbody tr:not(.week-divider-tr)")
                new_count = 0
                for m_row in mu_rows:
                    tds = m_row.find_elements(By.TAG_NAME, "td")
                    if len(tds) < 4: continue
                    m_date = parse_date(tds[0].text.strip())
                    if m_date > max_date:
                        category_data.append({
                            "id": current_id,
                            "시즌": target['season_id'],
                            "공연장명": place_id,
                            "날짜": m_date.strftime("%Y-%m-%d"),
                            "시간": f"{tds[2].text.strip()}:00",
                            "배우": f"[{tds[3].text.strip().replace(' ', '')}]"
                        })
                        current_id += 1
                        new_count += 1

                if new_count > 0:
                    log(f"   ✅ {new_count}개 신규 스케줄")

            except Exception as e:
                log(f"   ⚠️ 오류: {str(e)[:50]}")
                continue

        # 파일 저장
        if category_data:
            os.makedirs('downloads', exist_ok=True)
            fname = f"downloads/podoal_{conf['prefix']}_{datetime.now().strftime('%m%d_%H%M')}_{task_id[:8]}.xlsx"
            pd.DataFrame(category_data).to_excel(fname, index=False)
            task['file'] = fname
            task['count'] = len(category_data)
            log(f"\n✅ 완료! {len(category_data)}개 스케줄 저장됨")
        else:
            log("\n📭 신규 스케줄 없음")

        task['status'] = 'completed'

    except Exception as e:
        log(f"❌ 오류 발생: {e}")
        task['status'] = 'failed'
        task['error'] = str(e)
    finally:
        if driver:
            driver.quit()
        socketio.emit('task_complete', {'task_id': task_id, 'status': task['status']})

def run_import_task(task_id, username, password, file_path):
    """포도알에 엑셀 import"""
    task = tasks[task_id]
    task['status'] = 'running'
    task['logs'] = []

    def log(msg):
        task['logs'].append(msg)
        socketio.emit('log', {'task_id': task_id, 'message': msg})

    driver = None
    try:
        log("📤 포도알 Import 시작...")
        driver = setup_driver()

        # 로그인
        log("🔐 로그인 중...")
        driver.get("https://podor.co.kr/admin/login/")
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password + Keys.ENTER)
        time.sleep(2)
        log("✅ 로그인 완료")

        # 스케줄 페이지 이동
        driver.get("https://podor.co.kr/admin/performance/performanceschedule/")
        time.sleep(2)

        # Import 버튼 클릭
        wait = WebDriverWait(driver, 10)
        import_btn = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Import")))
        import_btn.click()
        time.sleep(2)

        # 파일 업로드
        file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
        abs_path = os.path.abspath(file_path)
        file_input.send_keys(abs_path)
        log(f"📁 파일 선택: {os.path.basename(file_path)}")
        time.sleep(1)

        # Submit
        submit_btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
        submit_btn.click()
        time.sleep(3)

        # Confirm import
        try:
            confirm_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit'][value='Confirm import']")))
            confirm_btn.click()
            time.sleep(3)
            log("✅ Import 완료!")
        except:
            log("⚠️ Confirm 버튼을 찾을 수 없습니다. 수동 확인 필요")

        task['status'] = 'completed'

    except Exception as e:
        log(f"❌ 오류: {e}")
        task['status'] = 'failed'
    finally:
        if driver:
            driver.quit()
        socketio.emit('task_complete', {'task_id': task_id, 'status': task['status']})

# ==========================================
# 라우트
# ==========================================
@app.route('/')
def index():
    return render_template('index.html', ticket_fields=TICKET_FIELDS)

@app.route('/api/crawl', methods=['POST'])
def start_crawl():
    data = request.json
    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        'id': task_id,
        'type': 'crawl',
        'status': 'pending',
        'logs': [],
        'file': None
    }

    filter_ids = parse_ids(data.get('filter_ids', ''))

    thread = threading.Thread(
        target=run_crawl_task,
        args=(task_id, data['username'], data['password'], data['category'], filter_ids),
        daemon=True
    )
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/api/import', methods=['POST'])
def start_import():
    data = request.json
    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        'id': task_id,
        'type': 'import',
        'status': 'pending',
        'logs': []
    }

    thread = threading.Thread(
        target=run_import_task,
        args=(task_id, data['username'], data['password'], data['file_path']),
        daemon=True
    )
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/api/task/<task_id>')
def get_task(task_id):
    if task_id in tasks:
        return jsonify(tasks[task_id])
    return jsonify({'error': 'Task not found'}), 404

@app.route('/api/download/<task_id>')
def download_file(task_id):
    if task_id in tasks and tasks[task_id].get('file'):
        return send_file(tasks[task_id]['file'], as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/season/<season_id>')
def get_season(season_id):
    """시즌 정보 조회 (티켓 URL용)"""
    # 이 기능은 로그인이 필요하므로 별도 구현 필요
    return jsonify({'message': 'Not implemented yet'})

if __name__ == '__main__':
    os.makedirs('downloads', exist_ok=True)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

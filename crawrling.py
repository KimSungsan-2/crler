import time
import re
import smtplib
import pandas as pd
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 1. 사용자 설정 (이메일 정보 입력 필수)
# ==========================================
PODOAL_ID = "podor"
PODOAL_PW = "tndlrckdcnfgkwk!"
MYUKIT_URL = "https://myukit.com/"

SENDER_EMAIL = "your_email@gmail.com" 
SENDER_PASSWORD = "your_app_password" 
RECEIVER_EMAIL = "target_email@gmail.com"

# 카테고리별 동적 설정
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
        "season_path": "/play_season/", # image_4383a1 반영
        "place_url": "https://podor.co.kr/admin/performance/performance_place/", # 뮤지컬과 동일
        "prefix": "play"
    }
}

# ==========================================
# 2. 유틸리티 함수
# ==========================================
def parse_date(date_str):
    if not date_str or date_str.strip() in ["-", ""]: return datetime(2000, 1, 1)
    # 영문 월(March, Feb 등) 및 한국어 월 대응
    clean_str = date_str.strip().replace(",", "").replace(".", "")
    clean_str = re.sub(r'\(.*?\)', '', clean_str).strip()
    formats = ["%Y-%m-%d", "%b %d %Y", "%B %d %Y", "%m월 %d일"]
    for fmt in formats:
        try:
            if fmt == "%m월 %d일":
                match = re.search(r'(\d+)월\s+(\d+)일', clean_str)
                if match: return datetime(2026, int(match.group(1)), int(match.group(2)))
            else: return datetime.strptime(clean_str, fmt)
        except ValueError: continue
    return datetime(2000, 1, 1)

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless') 
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def send_email(file_paths):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[{datetime.now().strftime('%m/%d')}] 포도알 뮤지컬/연극 신규 스케줄"
    
    for f_path in file_paths:
        with open(f_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename= {f_path}")
            msg.attach(part)
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("📧 통합 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

# ==========================================
# 3. 크롤링 핵심 함수
# ==========================================
def run_scrape(driver, category):
    conf = CONFIG[category]
    wait = WebDriverWait(driver, 15)
    category_data = []

    print(f"\n🚀 {category.upper()} 작업 시작...")

    # [A] 실시간 ID 추출 - 테이블 첫 번째 행(가장 최근)의 ID + 1
    driver.get(f"{conf['base_url']}{conf['schedule_path']}")
    time.sleep(3)
    try:
        first_row = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result_list tbody tr:first-child")))
        first_id = int(first_row.find_element(By.CSS_SELECTOR, "th.field-id, td.field-id").text.strip())
        current_id = first_id + 1
        print(f"   -> 실시간 {category} 시작 ID: {current_id} (최근 ID: {first_id})")
    except:
        print(f"   ⚠️ {category} ID 추출 실패.") ; return None

    # [B] 티켓오픈 대상 수집
    driver.get(f"{conf['base_url']}{conf['open_path']}")
    rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#result_list tbody tr")))
    targets = []
    for row in rows:
        cells = row.find_elements(By.CSS_SELECTOR, "td, th")
        if len(cells) >= 6 and cells[5].text.strip() == "-":
            targets.append({"title": cells[1].text.strip(), "season_id": cells[2].text.strip()})

    for target in targets:
        perf_name = target['title']
        print(f"🔍 '{perf_name}' 분석 중...")
        try:
            # 1. 공연장 ID 확인 (image_4383a1 반영: Place는 index 5)
            driver.get(f"{conf['base_url']}{conf['season_path']}?q={target['season_id']}")
            s_row = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result_list tbody tr:first-child")))
            place_name = s_row.find_elements(By.TAG_NAME, "td")[4].text.strip() # 시즌정리 테이블 기준
            
            driver.get(f"{conf['place_url']}?q={place_name}")
            place_id = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "th.field-id, td.field-id"))).text.strip()

            # 2. 어드민 최신 날짜 확인 (중복 방지) - 공연명으로 검색, 날짜 내림차순 정렬
            schedule_url = f"{conf['base_url']}{conf['schedule_path']}?q={perf_name}&o=-2"
            print(f"   [DEBUG] 스케줄 검색 URL (공연명: {perf_name}): {schedule_url}")
            driver.get(schedule_url)
            max_date = datetime(2000, 1, 1)
            try:
                sc_rows = WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#result_list tbody tr")))
                print(f"   [DEBUG] 검색된 행 수: {len(sc_rows)}")
                if sc_rows:
                    # 디버깅: 첫 행의 모든 컬럼 출력
                    all_tds = sc_rows[0].find_elements(By.TAG_NAME, "td")
                    print(f"   [DEBUG] 컬럼 개수: {len(all_tds)}")
                    for idx, td in enumerate(all_tds):
                        print(f"   [DEBUG] 컬럼{idx}: '{td.text.strip()}'")

                    # 모든 행에서 최신 날짜 찾기
                    for sc_row in sc_rows:
                        tds = sc_row.find_elements(By.TAG_NAME, "td")
                        for td in tds:
                            td_text = td.text.strip()
                            parsed = None
                            # 1) YYYY-MM-DD 형식
                            if re.match(r'^\d{4}-\d{2}-\d{2}$', td_text):
                                parsed = datetime.strptime(td_text, "%Y-%m-%d")
                            # 2) "Feb. 22, 2026" 형식 (약어+마침표)
                            elif re.match(r'^[A-Za-z]+\.\s*\d{1,2},\s*\d{4}$', td_text):
                                try:
                                    clean = td_text.replace(".", "")
                                    parsed = datetime.strptime(clean, "%b %d, %Y")
                                except ValueError:
                                    pass
                            # 3) "March 2, 2026" 형식 (전체 월 이름)
                            elif re.match(r'^[A-Za-z]+ \d{1,2}, \d{4}$', td_text):
                                try:
                                    parsed = datetime.strptime(td_text, "%B %d, %Y")
                                except ValueError:
                                    pass
                            if parsed and parsed > max_date:
                                max_date = parsed
                    if max_date > datetime(2000, 1, 1):
                        print(f"   -> 어드민 최신 날짜: {max_date.strftime('%Y-%m-%d')}")
                    else:
                        print(f"   [DEBUG] 날짜 파싱 실패 - max_date 여전히 2000-01-01")
            except Exception as e:
                print(f"   [DEBUG] 어드민 날짜 확인 실패: {e}")

            # 3. 뮤킷 검색 (드롭다운 3초 대기)
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
                time.sleep(2); driver.find_element(By.ID, "show-list-btn").click(); time.sleep(2)
            except: 
                print(f"   ⏩ '{perf_name}' 뮤킷 데이터 없음 (스킵)")
                continue

            # 4. 데이터 필터링 및 ID 부여
            mu_rows = driver.find_elements(By.CSS_SELECTOR, ".actor-schedule-list-table tbody tr:not(.week-divider-tr)")
            for m_row in mu_rows:
                tds = m_row.find_elements(By.TAG_NAME, "td")
                if len(tds) < 4: continue
                m_date = parse_date(tds[0].text.strip())
                if m_date > max_date:
                    category_data.append({
                        "id": current_id, "시즌": target['season_id'], "공연장명": place_id,
                        "날짜": m_date.strftime("%Y-%m-%d"), "시간": f"{tds[2].text.strip()}:00",
                        "배우": f"[{tds[3].text.strip().replace(' ', '')}]"
                    })
                    current_id += 1
        except Exception as e:
            print(f"   ⚠️ 오류 발생: {e}")
            continue

    if category_data:
        fname = f"podoal_{conf['prefix']}_{datetime.now().strftime('%m%d_%H%M')}.xlsx"
        pd.DataFrame(category_data).to_excel(fname, index=False)
        return fname
    return None

# ==========================================
# 4. 실행 메인
# ==========================================
if __name__ == "__main__":
    driver = setup_driver()
    created_files = []
    try:
        driver.get("https://podor.co.kr/admin/login/")
        driver.find_element(By.NAME, "username").send_keys(PODOAL_ID)
        driver.find_element(By.NAME, "password").send_keys(PODOAL_PW + Keys.ENTER)
        time.sleep(2)

        # 1. 뮤지컬
        m_file = run_scrape(driver, "musical")
        if m_file:
            created_files.append(m_file)
            print(f"\n✅ 뮤지컬 캐스팅 저장 완료: {m_file}")
        else:
            print("\n📭 뮤지컬 신규 스케줄 없음")

        # 2. 연극 진행 여부 확인
        proceed = input("\n🎭 연극으로 진행할까요? (y/n): ").strip().lower()
        if proceed == 'y':
            p_file = run_scrape(driver, "play")
            if p_file:
                created_files.append(p_file)
                print(f"\n✅ 연극 캐스팅 저장 완료: {p_file}")
            else:
                print("\n📭 연극 신규 스케줄 없음")
        else:
            print("\n⏭️ 연극 크롤링 스킵")

        if created_files:
            send_email(created_files)
    finally:
        driver.quit()
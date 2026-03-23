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
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# 환경변수에서 설정 로드
# ==========================================
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

# ==========================================
# 유틸리티
# ==========================================
def parse_date(date_str):
    if not date_str or date_str.strip() in ["-", ""]:
        return datetime(2000, 1, 1)
    clean_str = date_str.strip().replace(",", "").replace(".", "")
    clean_str = re.sub(r'\(.*?\)', '', clean_str).strip()
    formats = ["%Y-%m-%d", "%b %d %Y", "%B %d %Y", "%m월 %d일"]
    for fmt in formats:
        try:
            if fmt == "%m월 %d일":
                match = re.search(r'(\d+)월\s+(\d+)일', clean_str)
                if match:
                    return datetime(2026, int(match.group(1)), int(match.group(2)))
            else:
                return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
    return datetime(2000, 1, 1)


def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(options=options)


# ==========================================
# 크롤링
# ==========================================
def run_scrape(driver, category):
    conf = CONFIG[category]
    wait = WebDriverWait(driver, 15)
    category_data = []
    scraped_titles = []  # 실제로 스케줄을 가져온 공연 제목 목록

    print(f"\n🚀 {category.upper()} 크롤링 시작...")

    # [A] 실시간 ID 추출
    driver.get(f"{conf['base_url']}{conf['schedule_path']}")
    time.sleep(3)
    try:
        first_row = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#result_list tbody tr:first-child")
        ))
        first_id = int(first_row.find_element(
            By.CSS_SELECTOR, "th.field-id, td.field-id"
        ).text.strip())
        current_id = first_id + 1
        print(f"   -> 시작 ID: {current_id} (최근 ID: {first_id})")
    except Exception:
        print("   ⚠️ ID 추출 실패.")
        return None

    # [B] 티켓오픈 대상 수집
    driver.get(f"{conf['base_url']}{conf['open_path']}")
    rows = wait.until(EC.presence_of_all_elements_located(
        (By.CSS_SELECTOR, "#result_list tbody tr")
    ))
    targets = []
    for row in rows:
        cells = row.find_elements(By.CSS_SELECTOR, "td, th")
        if len(cells) >= 6 and cells[5].text.strip() == "-":
            targets.append({
                "title": cells[1].text.strip(),
                "season_id": cells[2].text.strip()
            })

    print(f"   -> 대상 공연 수: {len(targets)}")

    for idx, target in enumerate(targets):
        perf_name = target['title']
        print(f"🔍 [{idx+1}/{len(targets)}] '{perf_name}' 분석 중...")
        try:
            # 1. 공연장 ID 확인
            driver.get(f"{conf['base_url']}{conf['season_path']}?q={target['season_id']}")
            s_row = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#result_list tbody tr:first-child")
            ))
            place_name = s_row.find_elements(By.TAG_NAME, "td")[4].text.strip()

            driver.get(f"{conf['place_url']}?q={place_name}")
            place_id = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "th.field-id, td.field-id")
            )).text.strip()

            # 2. 어드민 최신 날짜 확인 (중복 방지)
            driver.get(f"{conf['base_url']}{conf['schedule_path']}?q={perf_name}&o=-2")
            max_date = datetime(2000, 1, 1)
            try:
                sc_rows = WebDriverWait(driver, 5).until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "#result_list tbody tr")
                    )
                )
                for sc_row in sc_rows:
                    for td in sc_row.find_elements(By.TAG_NAME, "td"):
                        td_text = td.text.strip()
                        parsed = None
                        if re.match(r'^\d{4}-\d{2}-\d{2}$', td_text):
                            parsed = datetime.strptime(td_text, "%Y-%m-%d")
                        elif re.match(r'^[A-Za-z]+\.\s*\d{1,2},\s*\d{4}$', td_text):
                            try:
                                parsed = datetime.strptime(
                                    td_text.replace(".", ""), "%b %d, %Y"
                                )
                            except ValueError:
                                pass
                        elif re.match(r'^[A-Za-z]+ \d{1,2}, \d{4}$', td_text):
                            try:
                                parsed = datetime.strptime(td_text, "%B %d, %Y")
                            except ValueError:
                                pass
                        if parsed and parsed > max_date:
                            max_date = parsed
                if max_date > datetime(2000, 1, 1):
                    print(f"   -> 최신 날짜: {max_date.strftime('%Y-%m-%d')}")
            except Exception:
                pass

            # 3. 뮤킷 검색
            driver.get(MYUKIT_URL)
            search = wait.until(EC.presence_of_element_located((By.ID, "sch-v1-input")))
            search.clear()
            search.send_keys(re.sub(r'\[.*?\]', '', perf_name).strip())
            try:
                res = WebDriverWait(driver, 3).until(
                    EC.visibility_of_element_located((By.ID, "sch-v1-results"))
                )
                items = res.find_elements(By.TAG_NAME, "li")
                clicked = False
                for i in items:
                    if "진행 중" in i.text:
                        i.click()
                        clicked = True
                        break
                if not clicked:
                    items[0].click()
                time.sleep(2)
                driver.find_element(By.ID, "show-list-btn").click()
                time.sleep(2)
            except Exception:
                print(f"   ⏩ '{perf_name}' 뮤킷 데이터 없음 (스킵)")
                continue

            # 4. 데이터 필터링 및 ID 부여
            mu_rows = driver.find_elements(
                By.CSS_SELECTOR,
                ".actor-schedule-list-table tbody tr:not(.week-divider-tr)"
            )
            new_count = 0
            for m_row in mu_rows:
                tds = m_row.find_elements(By.TAG_NAME, "td")
                if len(tds) < 4:
                    continue
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
                scraped_titles.append(perf_name)
                print(f"   ✅ {new_count}개 신규 스케줄")

        except Exception as e:
            print(f"   ⚠️ 오류: {str(e)[:80]}")
            continue

    if category_data:
        fname = f"podoal_{conf['prefix']}_{datetime.now().strftime('%m%d_%H%M')}.xlsx"
        pd.DataFrame(category_data).to_excel(fname, index=False)
        print(f"\n✅ {len(category_data)}개 스케줄 저장: {fname}")
        return fname, scraped_titles
    return None, scraped_titles


# ==========================================
# Import
# ==========================================
def run_import(driver, category, file_path):
    conf = CONFIG[category]
    wait = WebDriverWait(driver, 15)

    import_url = f"{conf['base_url']}{conf['schedule_path']}import/"
    print(f"\n📤 Import 시작: {import_url}")
    driver.get(import_url)
    time.sleep(2)

    # 파일 업로드
    file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
    file_input.send_keys(os.path.abspath(file_path))
    print(f"   -> 파일 선택: {os.path.basename(file_path)}")

    # Format 드롭다운에서 xlsx 선택 (name이 "format" 또는 "input_format"일 수 있음)
    format_el = None
    for name_attr in ("format", "input_format"):
        try:
            format_el = wait.until(
                EC.presence_of_element_located((By.NAME, name_attr))
            )
            break
        except Exception:
            continue
    if format_el is None:
        raise Exception("Format 드롭다운을 찾을 수 없습니다 (name='format' / 'input_format' 모두 실패)")
    format_select = Select(format_el)
    try:
        format_select.select_by_visible_text("xlsx")
    except Exception:
        for option in format_select.options:
            if "xlsx" in option.text.lower():
                option.click()
                break
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


# ==========================================
# 티켓오픈 처리
# ==========================================
def handle_ticket_open(driver, category, scraped_titles=None):
    conf = CONFIG[category]
    wait = WebDriverWait(driver, 15)
    today = date.today()

    open_url = f"{conf['base_url']}{conf['open_path']}"
    print(f"\n🎫 티켓오픈 처리 시작: {open_url}")
    driver.get(open_url)
    time.sleep(2)

    rows = driver.find_elements(By.CSS_SELECTOR, "#result_list tbody tr")
    if not rows:
        print("   -> 티켓오픈 항목 없음")
        return {"deleted": 0, "updated": 0, "skipped": 0}

    items_to_delete = []
    items_to_update = []
    items_skipped = []

    for row in rows:
        cells = row.find_elements(By.CSS_SELECTOR, "td, th")
        # 컬럼: 체크박스(0), 공연명(1), 시즌id(2), 오픈날짜(3), 오픈시간(4), 스케줄반영(5)
        if len(cells) < 6:
            continue

        open_date_str = cells[3].text.strip()
        schedule_status = cells[5].text.strip()
        perf_name = cells[1].text.strip()

        try:
            open_date = datetime.strptime(open_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        checkbox = row.find_element(By.CSS_SELECTOR, "input.action-select")
        checkbox_value = checkbox.get_attribute("value")

        if open_date < today:
            # 오늘 이전 (엄격히 과거만) → 삭제 대상
            items_to_delete.append((checkbox_value, perf_name, open_date_str))
        elif schedule_status != "반영 완료":
            # 실제로 스케줄이 가져와진 공연만 반영완료 처리
            if scraped_titles is not None and perf_name not in scraped_titles:
                items_skipped.append(perf_name)
                print(f"   ⏭️ '{perf_name}' 스케줄 미반영 (크롤링 데이터 없음) - 반영완료 처리 보류")
            else:
                link = cells[1].find_element(By.TAG_NAME, "a")
                items_to_update.append((link.get_attribute("href"), perf_name))

    updated_count = 0
    deleted_count = 0

    # 1) 반영완료 처리 (먼저 - 삭제하면 페이지가 변경되므로)
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

        for value, name, date_str in items_to_delete:
            print(f"   -> '{name}' ({date_str}) 삭제 대상 선택")
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

    print(f"   -> 처리 완료: 삭제 {deleted_count}건, 반영완료 {updated_count}건, 보류 {len(items_skipped)}건")
    return {"deleted": deleted_count, "updated": updated_count, "skipped": len(items_skipped)}


# ==========================================
# 이메일 발송
# ==========================================
def send_result_email(category, file_path, scrape_count, ticket_result, error=None):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL

    if error:
        msg['Subject'] = f"[포도알 자동화] ❌ {category.upper()} 오류 - {datetime.now().strftime('%m/%d')}"
        body = f"오류 발생:\n{error}"
    else:
        msg['Subject'] = f"[포도알 자동화] ✅ {category.upper()} 완료 - {datetime.now().strftime('%m/%d')}"
        body = (
            f"포도알 {category.upper()} 자동화 결과\n\n"
            f"■ 크롤링: {scrape_count}개 신규 스케줄\n"
            f"■ 티켓오픈: 삭제 {ticket_result['deleted']}건, "
            f"반영완료 {ticket_result['updated']}건, "
            f"보류 {ticket_result.get('skipped', 0)}건\n"
            f"■ Import: {'완료' if scrape_count > 0 else '스킵 (신규 없음)'}\n"
        )

    msg.attach(MIMEText(body, 'plain'))

    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(file_path)}"
            )
            msg.attach(part)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("📧 이메일 발송 완료")


# ==========================================
# 메인
# ==========================================
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
        file_path, scraped_titles = run_scrape(driver, category)
        if file_path:
            scrape_count = len(pd.read_excel(file_path))

            # 3. Import
            run_import(driver, category, file_path)
        else:
            print("\n📭 신규 스케줄 없음 - Import 스킵")

        # 4. 티켓오픈 처리 (실제 크롤링된 공연 목록 전달)
        ticket_result = handle_ticket_open(driver, category, scraped_titles)

        # 5. 이메일 발송
        send_result_email(category, file_path, scrape_count, ticket_result)

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        if driver:
            try:
                driver.save_screenshot("error_screenshot.png")
            except Exception:
                pass
        try:
            send_result_email(category, file_path, scrape_count, ticket_result, error=str(e))
        except Exception:
            print("이메일 발송도 실패")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()

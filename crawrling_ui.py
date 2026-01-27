import time
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

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

# 티켓 플랫폼 필드 매핑 (라벨: field_key, element_id)
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
# 유틸리티 함수
# ==========================================
def parse_ids(id_string):
    """ID 문자열 파싱: '1717, 1719' 또는 '1717~1719' 형식 지원"""
    ids = []
    id_string = id_string.strip()
    if not id_string:
        return ids

    parts = [p.strip() for p in id_string.replace(' ', '').split(',')]
    for part in parts:
        if '~' in part:
            try:
                start, end = part.split('~')
                ids.extend(range(int(start), int(end) + 1))
            except:
                pass
        elif '-' in part and not part.startswith('-'):
            try:
                start, end = part.split('-')
                ids.extend(range(int(start), int(end) + 1))
            except:
                pass
        else:
            try:
                ids.append(int(part))
            except:
                pass
    return ids

def parse_date(date_str):
    if not date_str or date_str.strip() in ["-", ""]: return datetime(2000, 1, 1)
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

def setup_driver(headless=True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


# ==========================================
# GUI 애플리케이션
# ==========================================
class CrawlerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("포도알 스케줄 크롤러")
        self.root.geometry("850x750")
        self.root.resizable(True, True)

        self.driver = None
        self.created_files = []
        self.is_running = False
        self.ticket_entries = {}

        self.setup_ui()

    def setup_ui(self):
        # 노트북 (탭)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # === 탭 1: 티켓 URL 등록 ===
        self.tab_ticket = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_ticket, text="1️⃣ 티켓 URL 등록")
        self.setup_ticket_tab()

        # === 탭 2: 캐스팅 크롤링 ===
        self.tab_crawl = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_crawl, text="2️⃣ 캐스팅 크롤링")
        self.setup_crawl_tab()

        # === 공통: 로그인 프레임 (하단) ===
        login_frame = ttk.LabelFrame(self.root, text="로그인 정보", padding="5")
        login_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        ttk.Label(login_frame, text="ID:").pack(side=tk.LEFT, padx=(0, 5))
        self.id_entry = ttk.Entry(login_frame, width=15)
        self.id_entry.pack(side=tk.LEFT)
        self.id_entry.insert(0, "podor")

        ttk.Label(login_frame, text="PW:").pack(side=tk.LEFT, padx=(15, 5))
        self.pw_entry = ttk.Entry(login_frame, width=20, show="*")
        self.pw_entry.pack(side=tk.LEFT)
        self.pw_entry.insert(0, "tndlrckdcnfgkwk!")

        self.headless_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(login_frame, text="백그라운드 실행", variable=self.headless_var).pack(side=tk.LEFT, padx=(20, 0))

    def setup_ticket_tab(self):
        """티켓 URL 등록 탭 구성"""
        main_frame = ttk.Frame(self.tab_ticket, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 시즌 ID 입력
        id_frame = ttk.LabelFrame(main_frame, text="시즌 ID 입력", padding="10")
        id_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(id_frame, text="시즌 ID:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.season_id_entry = ttk.Entry(id_frame, width=40)
        self.season_id_entry.grid(row=0, column=1, sticky=tk.W)
        ttk.Label(id_frame, text="예: 1717, 1719 또는 1717~1720", foreground="gray").grid(row=0, column=2, padx=(10, 0))

        ttk.Button(id_frame, text="🔍 시즌 정보 불러오기", command=self.load_season_info).grid(row=0, column=3, padx=(10, 0))

        # 현재 선택된 시즌 정보
        self.season_info_label = ttk.Label(id_frame, text="", foreground="blue")
        self.season_info_label.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))

        # 티켓 URL 입력 폼
        ticket_frame = ttk.LabelFrame(main_frame, text="티켓 플랫폼 URL", padding="10")
        ticket_frame.pack(fill=tk.X, pady=(0, 10))

        # 2열로 배치
        for i, (label, field_name) in enumerate(TICKET_FIELDS):
            row = i // 2
            col = (i % 2) * 2

            ttk.Label(ticket_frame, text=f"{label}:").grid(row=row, column=col, sticky=tk.W, padx=(0 if col == 0 else 20, 5), pady=2)
            entry = ttk.Entry(ticket_frame, width=35)
            entry.grid(row=row, column=col+1, sticky=tk.W, pady=2)
            self.ticket_entries[field_name] = entry

        # 버튼
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.save_ticket_btn = ttk.Button(btn_frame, text="💾 URL 저장", command=self.save_ticket_urls, width=20)
        self.save_ticket_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.clear_ticket_btn = ttk.Button(btn_frame, text="🗑 초기화", command=self.clear_ticket_form, width=15)
        self.clear_ticket_btn.pack(side=tk.LEFT)

        self.next_season_btn = ttk.Button(btn_frame, text="➡️ 다음 시즌", command=self.next_season, width=15, state=tk.DISABLED)
        self.next_season_btn.pack(side=tk.LEFT, padx=(10, 0))

        # 로그
        log_frame = ttk.LabelFrame(main_frame, text="진행 상황", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.ticket_log = scrolledtext.ScrolledText(log_frame, height=12, state=tk.DISABLED, font=("Consolas", 9))
        self.ticket_log.pack(fill=tk.BOTH, expand=True)

    def setup_crawl_tab(self):
        """캐스팅 크롤링 탭 구성"""
        main_frame = ttk.Frame(self.tab_crawl, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 공연 ID 필터 (선택적)
        filter_frame = ttk.LabelFrame(main_frame, text="공연 ID 필터 (선택사항)", padding="10")
        filter_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(filter_frame, text="특정 시즌 ID만:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.crawl_id_entry = ttk.Entry(filter_frame, width=40)
        self.crawl_id_entry.grid(row=0, column=1, sticky=tk.W)
        ttk.Label(filter_frame, text="비워두면 티켓오픈 전체 대상", foreground="gray").grid(row=0, column=2, padx=(10, 0))

        # 실행 버튼
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = ttk.Button(btn_frame, text="🚀 뮤지컬 크롤링 시작", command=self.start_musical, width=25)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.play_btn = ttk.Button(btn_frame, text="🎭 연극 크롤링 시작", command=self.start_play, width=25, state=tk.DISABLED)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(btn_frame, text="⏹ 중지", command=self.stop_crawling, width=10, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        # 로그
        log_frame = ttk.LabelFrame(main_frame, text="진행 상황", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, state=tk.DISABLED, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 결과
        result_frame = ttk.LabelFrame(main_frame, text="생성된 파일", padding="5")
        result_frame.pack(fill=tk.X, pady=(10, 0))

        self.result_label = ttk.Label(result_frame, text="아직 생성된 파일 없음")
        self.result_label.pack(anchor=tk.W)

    # ==========================================
    # 티켓 URL 등록 기능
    # ==========================================
    def ticket_log_msg(self, message):
        self.ticket_log.config(state=tk.NORMAL)
        self.ticket_log.insert(tk.END, f"{message}\n")
        self.ticket_log.see(tk.END)
        self.ticket_log.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def load_season_info(self):
        """시즌 ID로 정보 불러오기"""
        id_str = self.season_id_entry.get().strip()
        if not id_str:
            messagebox.showwarning("경고", "시즌 ID를 입력하세요.")
            return

        self.season_ids = parse_ids(id_str)
        if not self.season_ids:
            messagebox.showwarning("경고", "올바른 ID 형식이 아닙니다.")
            return

        self.current_season_idx = 0
        self.ticket_log_msg(f"📋 총 {len(self.season_ids)}개 시즌: {self.season_ids}")

        # 첫 번째 시즌 로드
        thread = threading.Thread(target=self.load_single_season, daemon=True)
        thread.start()

    def load_single_season(self):
        """단일 시즌 정보 로드"""
        if self.current_season_idx >= len(self.season_ids):
            self.ticket_log_msg("\n✅ 모든 시즌 처리 완료!")
            self.root.after(0, lambda: self.next_season_btn.config(state=tk.DISABLED))
            return

        season_id = self.season_ids[self.current_season_idx]
        self.current_season_id = season_id

        try:
            if not self.driver:
                self.ticket_log_msg("🔐 포도알 로그인 중...")
                self.driver = setup_driver(self.headless_var.get())
                self.driver.get("https://podor.co.kr/admin/login/")
                self.driver.find_element(By.NAME, "username").send_keys(self.id_entry.get())
                self.driver.find_element(By.NAME, "password").send_keys(self.pw_entry.get() + Keys.ENTER)
                time.sleep(2)
                self.ticket_log_msg("✅ 로그인 완료")

            # 시즌 페이지 접속
            url = f"https://podor.co.kr/admin/performance/performance_season/{season_id}/change/"
            self.ticket_log_msg(f"\n🔍 시즌 {season_id} 정보 로드 중...")
            self.driver.get(url)
            time.sleep(1)

            wait = WebDriverWait(self.driver, 10)

            # 공연명 가져오기
            try:
                perf_name = wait.until(EC.presence_of_element_located((By.ID, "id_performance"))).find_element(By.CSS_SELECTOR, "option[selected]").text
            except:
                perf_name = "알 수 없음"

            self.root.after(0, lambda: self.season_info_label.config(text=f"현재: [{season_id}] {perf_name} ({self.current_season_idx + 1}/{len(self.season_ids)})"))

            # 기존 URL 값 불러오기 (TICKET_FIELDS 사용)
            for label, field_key in TICKET_FIELDS:
                try:
                    element_id = f"id_{field_key}"
                    value = self.driver.find_element(By.ID, element_id).get_attribute("value") or ""
                    self.root.after(0, lambda fk=field_key, v=value: self.set_entry_value(fk, v))
                except:
                    pass

            self.ticket_log_msg(f"✅ [{season_id}] {perf_name} 정보 로드 완료")

            # 다음 버튼 활성화
            if len(self.season_ids) > 1:
                self.root.after(0, lambda: self.next_season_btn.config(state=tk.NORMAL))

        except Exception as e:
            self.ticket_log_msg(f"❌ 오류: {e}")

    def set_entry_value(self, field_name, value):
        """Entry 값 설정"""
        if field_name in self.ticket_entries:
            self.ticket_entries[field_name].delete(0, tk.END)
            self.ticket_entries[field_name].insert(0, value)

    def save_ticket_urls(self):
        """티켓 URL 저장"""
        if not hasattr(self, 'current_season_id'):
            messagebox.showwarning("경고", "먼저 시즌 정보를 불러오세요.")
            return

        thread = threading.Thread(target=self._save_ticket_urls_thread, daemon=True)
        thread.start()

    def _save_ticket_urls_thread(self):
        """URL 저장 스레드"""
        try:
            season_id = self.current_season_id
            url = f"https://podor.co.kr/admin/performance/performance_season/{season_id}/change/"

            if self.driver.current_url != url:
                self.driver.get(url)
                time.sleep(1)

            # 값 입력 (TICKET_FIELDS 사용)
            for label, field_key in TICKET_FIELDS:
                try:
                    element_id = f"id_{field_key}"
                    value = self.ticket_entries[field_key].get()
                    element = self.driver.find_element(By.ID, element_id)
                    element.clear()
                    element.send_keys(value)
                except:
                    pass

            # 저장 버튼 클릭
            save_btn = self.driver.find_element(By.NAME, "_save")
            save_btn.click()
            time.sleep(2)

            self.ticket_log_msg(f"💾 시즌 {season_id} URL 저장 완료!")

        except Exception as e:
            self.ticket_log_msg(f"❌ 저장 오류: {e}")

    def clear_ticket_form(self):
        """폼 초기화"""
        for entry in self.ticket_entries.values():
            entry.delete(0, tk.END)

    def next_season(self):
        """다음 시즌으로 이동"""
        self.current_season_idx += 1
        self.clear_ticket_form()
        thread = threading.Thread(target=self.load_single_season, daemon=True)
        thread.start()

    # ==========================================
    # 캐스팅 크롤링 기능
    # ==========================================
    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def start_musical(self):
        if self.is_running:
            return
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.created_files = []

        # ID 필터 파싱
        self.filter_ids = parse_ids(self.crawl_id_entry.get())
        if self.filter_ids:
            self.log(f"📋 필터 적용: {self.filter_ids}")

        thread = threading.Thread(target=self.run_musical_crawl, daemon=True)
        thread.start()

    def start_play(self):
        if self.is_running:
            return
        self.is_running = True
        self.play_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        thread = threading.Thread(target=self.run_play_crawl, daemon=True)
        thread.start()

    def stop_crawling(self):
        self.is_running = False
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        self.log("⏹ 크롤링 중지됨")
        self.reset_buttons()

    def reset_buttons(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.is_running = False

    def login(self):
        self.log("🔐 포도알 로그인 중...")
        self.driver = setup_driver(self.headless_var.get())
        self.driver.get("https://podor.co.kr/admin/login/")
        self.driver.find_element(By.NAME, "username").send_keys(self.id_entry.get())
        self.driver.find_element(By.NAME, "password").send_keys(self.pw_entry.get() + Keys.ENTER)
        time.sleep(2)
        self.log("✅ 로그인 완료")

    def run_musical_crawl(self):
        try:
            if not self.driver:
                self.login()

            result = self.run_scrape("musical")

            if result:
                self.created_files.append(result)
                self.log(f"\n✅ 뮤지컬 캐스팅 저장 완료: {result}")
                self.update_result_label()
            else:
                self.log("\n📭 뮤지컬 신규 스케줄 없음")

            self.root.after(0, self.ask_play_confirmation)

        except Exception as e:
            self.log(f"❌ 오류 발생: {e}")
            self.cleanup()

    def ask_play_confirmation(self):
        self.stop_btn.config(state=tk.DISABLED)
        result = messagebox.askyesno("연극 크롤링", "🎭 연극으로 진행할까요?")
        if result:
            self.play_btn.config(state=tk.NORMAL)
            self.log("\n🎭 연극 버튼이 활성화되었습니다.")
        else:
            self.log("\n⏭️ 연극 크롤링 스킵")
            self.cleanup()

    def run_play_crawl(self):
        try:
            if not self.driver:
                self.login()

            result = self.run_scrape("play")

            if result:
                self.created_files.append(result)
                self.log(f"\n✅ 연극 캐스팅 저장 완료: {result}")
                self.update_result_label()
            else:
                self.log("\n📭 연극 신규 스케줄 없음")

            self.cleanup()

        except Exception as e:
            self.log(f"❌ 오류 발생: {e}")
            self.cleanup()

    def cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        self.reset_buttons()
        self.play_btn.config(state=tk.DISABLED)

    def update_result_label(self):
        if self.created_files:
            self.result_label.config(text=", ".join(self.created_files))

    def run_scrape(self, category):
        conf = CONFIG[category]
        wait = WebDriverWait(self.driver, 15)
        category_data = []

        self.log(f"\n🚀 {category.upper()} 작업 시작...")

        # [A] 실시간 ID 추출
        self.driver.get(f"{conf['base_url']}{conf['schedule_path']}")
        time.sleep(3)
        try:
            first_row = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result_list tbody tr:first-child")))
            first_id = int(first_row.find_element(By.CSS_SELECTOR, "th.field-id, td.field-id").text.strip())
            current_id = first_id + 1
            self.log(f"   -> 시작 ID: {current_id} (최근 ID: {first_id})")
        except:
            self.log(f"   ⚠️ {category} ID 추출 실패.")
            return None

        # [B] 티켓오픈 대상 수집
        self.driver.get(f"{conf['base_url']}{conf['open_path']}")
        rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#result_list tbody tr")))
        targets = []
        for row in rows:
            cells = row.find_elements(By.CSS_SELECTOR, "td, th")
            if len(cells) >= 6 and cells[5].text.strip() == "-":
                season_id = cells[2].text.strip()
                # 필터 적용
                if self.filter_ids:
                    try:
                        if int(season_id) not in self.filter_ids:
                            continue
                    except:
                        continue
                targets.append({"title": cells[1].text.strip(), "season_id": season_id})

        self.log(f"   -> 대상 공연 수: {len(targets)}")

        for target in targets:
            if not self.is_running:
                break

            perf_name = target['title']
            self.log(f"🔍 '{perf_name}' (ID: {target['season_id']}) 분석 중...")
            try:
                # 1. 공연장 ID 확인
                self.driver.get(f"{conf['base_url']}{conf['season_path']}?q={target['season_id']}")
                s_row = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result_list tbody tr:first-child")))
                place_name = s_row.find_elements(By.TAG_NAME, "td")[4].text.strip()

                self.driver.get(f"{conf['place_url']}?q={place_name}")
                place_id = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "th.field-id, td.field-id"))).text.strip()

                # 2. 어드민 최신 날짜 확인
                schedule_url = f"{conf['base_url']}{conf['schedule_path']}?q={perf_name}&o=-2"
                self.driver.get(schedule_url)
                max_date = datetime(2000, 1, 1)
                try:
                    sc_rows = WebDriverWait(self.driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#result_list tbody tr")))
                    if sc_rows:
                        for sc_row in sc_rows:
                            tds = sc_row.find_elements(By.TAG_NAME, "td")
                            for td in tds:
                                td_text = td.text.strip()
                                parsed = None
                                if re.match(r'^\d{4}-\d{2}-\d{2}$', td_text):
                                    parsed = datetime.strptime(td_text, "%Y-%m-%d")
                                elif re.match(r'^[A-Za-z]+\.\s*\d{1,2},\s*\d{4}$', td_text):
                                    try:
                                        clean = td_text.replace(".", "")
                                        parsed = datetime.strptime(clean, "%b %d, %Y")
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
                            self.log(f"   -> 어드민 최신 날짜: {max_date.strftime('%Y-%m-%d')}")
                except:
                    pass

                # 3. 뮤킷 검색
                self.driver.get(MYUKIT_URL)
                search = wait.until(EC.presence_of_element_located((By.ID, "sch-v1-input")))
                search.clear()
                search.send_keys(re.sub(r'\[.*?\]', '', perf_name).strip())
                try:
                    res = WebDriverWait(self.driver, 3).until(EC.visibility_of_element_located((By.ID, "sch-v1-results")))
                    items = res.find_elements(By.TAG_NAME, "li")
                    clicked = False
                    for i in items:
                        if "진행 중" in i.text: i.click(); clicked = True; break
                    if not clicked: items[0].click()
                    time.sleep(2); self.driver.find_element(By.ID, "show-list-btn").click(); time.sleep(2)
                except:
                    self.log(f"   ⏩ '{perf_name}' 뮤킷 데이터 없음 (스킵)")
                    continue

                # 4. 데이터 필터링
                mu_rows = self.driver.find_elements(By.CSS_SELECTOR, ".actor-schedule-list-table tbody tr:not(.week-divider-tr)")
                new_count = 0
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
                        new_count += 1

                if new_count > 0:
                    self.log(f"   ✅ {new_count}개 신규 스케줄 추가")

            except Exception as e:
                self.log(f"   ⚠️ 오류 발생: {e}")
                continue

        if category_data:
            fname = f"podoal_{conf['prefix']}_{datetime.now().strftime('%m%d_%H%M')}.xlsx"
            pd.DataFrame(category_data).to_excel(fname, index=False)
            return fname
        return None


# ==========================================
# 실행
# ==========================================
if __name__ == "__main__":
    root = tk.Tk()
    app = CrawlerApp(root)
    root.mainloop()

# GitHub Actions 자동화 설계

## 개요

포도알 스케줄 크롤러를 GitHub Actions로 자동화하여 수동 실행 없이 크롤링, Import, 티켓오픈 처리, 이메일 발송까지 전체 워크플로우를 자동 수행한다.

## 전체 플로우

```
GitHub Actions (cron/수동 트리거)
  → automate.py 실행
    → 1. 포도알 로그인 (1회)
    → 2. 크롤링 (뮤지컬 or 연극)
    → 3. Excel 생성
    → 4. Import: 업로드 → Submit → Confirm Import
    → 5. 티켓오픈 처리
       - 오픈날짜 지난 항목: 체크 → Delete → "Yes, I'm sure"
       - 오픈날짜 안 지난 항목: 상세 진입 → 스케줄반영 "반영완료" → Save
    → 6. 결과 이메일 발송
```

## 파일 구조

- `automate.py` - 자동화 전용 스크립트
- `.github/workflows/podoal-musical.yml` - 뮤지컬 (월/수/토 04:00 KST)
- `.github/workflows/podoal-play.yml` - 연극 (화/목/일 04:00 KST)

## 스케줄

| 카테고리 | 요일 | 시간 (KST) | cron (UTC) |
|---------|------|-----------|------------|
| 뮤지컬 | 월,수,토 | 04:00 | `0 19 * * 0,2,5` |
| 연극 | 화,목,일 | 04:00 | `0 19 * * 1,3,6` |

(KST = UTC + 9, 따라서 KST 04:00 = UTC 전날 19:00)

## GitHub Secrets

| Secret | 용도 |
|--------|------|
| `PODOAL_ID` | 포도알 로그인 ID |
| `PODOAL_PW` | 포도알 로그인 PW |
| `SENDER_EMAIL` | 발신 Gmail |
| `SENDER_PASSWORD` | Gmail 앱 비밀번호 |
| `RECEIVER_EMAIL` | 수신 이메일 |

## automate.py 주요 함수

### `run_scrape(driver, category)`
- 기존 crawrling.py 로직 재사용
- 티켓오픈 목록에서 스케줄반영="-"인 대상만 크롤링
- Excel 파일 생성 후 경로 반환

### `run_import(driver, category, file_path)`
- `/admin/performance/performanceschedule/import/` 이동
- `input[type='file']`에 Excel 업로드
- Format 드롭다운에서 xlsx 선택
- Submit 클릭 → Confirm Import 클릭

### `handle_ticket_open(driver, category)`
- 티켓오픈 페이지 이동
- 각 행의 오픈날짜 확인:
  - 오늘 이전: 체크박스 선택 (value 기반)
  - 오늘 이후: 상세 페이지 진입 → `id_스케줄반영`에 "반영완료" 입력 → Save
- 삭제 대상이 있으면: action=delete_selected 선택 → Go → "Yes, I'm sure"

### `send_result_email(results)`
- 크롤링 결과 요약 + Excel 첨부
- 에러 발생 시 에러 내용 포함

## 안전장치

1. 오픈날짜가 오늘인 항목은 삭제하지 않음 (엄격히 과거만)
2. 신규 스케줄 0건이면 Import 단계 스킵
3. 각 단계 실패 시 에러를 이메일로 발송
4. Selenium 세션 실패 시 스크린샷 저장

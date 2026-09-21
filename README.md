# 운수종사자 일상점검 시스템 v2 — Phase 1 운영형 개발본

기준 UI: `docs/ui_reference_v3.2.html`

## 구조

- 기사 Web/PWA: `/`
- 관리자 Web: `/admin`
- FastAPI: `/api/*`
- PostgreSQL: Railway `DATABASE_URL`
- 법정 점검표: `/print/legal-form?month=YYYY-MM`
- 관리자 법정 점검표: `/print/admin/legal-form/{member_id}?month=YYYY-MM`

프런트엔드는 DB에 직접 접근하지 않고 항상 `Web → FastAPI → PostgreSQL` 경로를 사용합니다.

## 실제 명부 매핑

업로드 받은 `택배회원`, `개인회원` 파일의 실제 헤더를 기준으로 구현했습니다.

- `management_number` → 관리번호 (관리자 전용)
- `region` → 지역
- `vehicle_number` → 차량번호
- `name` → 성명
- `category` → 개인/택배
- `address` → 주소
- `phone` → 전화번호
- `mobile` → 휴대폰번호
- `membership_status` → 전체면허자/협회 쪽 회원상태
- `certificate_number` → 자격증명발급번호 (관리자 전용)
- `vehicle_type` → 실제 차종

`membership_status`는 **일상점검 앱 가입상태와 별도**입니다.

개인정보가 포함된 원본 Excel은 Git 저장소에 넣지 않도록 `.gitignore`에서 `*.xlsx`, `*.xls`, `*.csv`를 제외했습니다.

## 로컬 실행

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env  # macOS/Linux

alembic upgrade head
uvicorn backend.app.main:app --reload --port 8000
```

브라우저:

- 기사: http://localhost:8000/
- 관리자: http://localhost:8000/admin
- API 문서: http://localhost:8000/docs

개발환경 관리자 기본값:

- ID: `admin`
- PW: `ChangeMe123!`
- TOTP: `000000` (`DEV_ADMIN_TOTP_BYPASS=true`일 때만)

운영환경에서는 반드시 관리자 비밀번호·TOTP secret·SESSION_SECRET·PIN_PEPPER를 Railway Variables로 교체하고 `DEV_ADMIN_TOTP_BYPASS=false`로 설정합니다.

## Railway

1. GitHub에 이 프로젝트를 push
2. Railway 프로젝트에서 GitHub 저장소 연결
3. PostgreSQL 추가
4. Variables 설정
   - `APP_ENV=production`
   - `DATABASE_URL` (Railway PostgreSQL이 제공)
   - `SESSION_SECRET`
   - `PIN_PEPPER`
   - `PUBLIC_ORIGIN=https://고정도메인`
   - `BOOTSTRAP_ADMIN_LOGIN`
   - `BOOTSTRAP_ADMIN_PASSWORD`
   - `BOOTSTRAP_ADMIN_TOTP_SECRET`
   - `DEV_ADMIN_TOTP_BYPASS=false`
5. Dockerfile 배포
6. `/health` 확인

## Google Play

Phase 3에서 현재 PWA를 TWA(Android)로 감싸 Google Play에 올리는 구조입니다. 운영 도메인은 Play 등록 전에 고정 커스텀 도메인으로 확정하는 것을 권장합니다.

## 구현된 Phase 1 기능

### 기사
- 차량번호 + 이름 최초 확인
- 주소 확인/변경요청
- 4자리 PIN 등록
- 세션 쿠키 자동 로그인
- 오늘 점검
- 법정 11개 점검항목
- 전체양호 / 불량항목 / 미운행
- 과거 미등록 처리
- 지연입력 속성
- `실제 점검하지 않음` 이벤트
- 월간 이력
- 법정 점검표 인쇄/PDF
- 차종/휴대폰/주소 표시

### 관리자
- 비밀번호 + TOTP 로그인
- 오늘 현황
- 앱 가입/미가입 분리
- 점검 미등록/미운행/이상/지연입력
- 이름/차량번호/차종/휴대폰/관리번호/자격증명발급번호 검색
- 회원 상세
- 관리번호/자격증명발급번호 관리자 전용 표시
- 월간 점검이력
- 관리자 대리입력
- PIN 초기화 + 세션/기기 폐기
- 주소 변경 승인/반려
- Excel 명부 미리보기/반영
- `full_snapshot` / `partial_update`
- 관리자 감사로그
- 시스템 설정 조회/수정 API

## 명부 안전 규칙

- 차량번호 정규화값을 우선 매칭합니다.
- 차량번호 매칭이 없을 때 `management_number + category`를 보조 매칭키로 사용합니다.
- 모호하면 `needs_review`로 보냅니다.
- `full_snapshot`의 누락자 inactive 후보는 **해당 category 범위만** 대상으로 합니다.
- `partial_update`는 파일에 없는 회원을 절대 inactive 처리하지 않습니다.
- 관리자가 `apply`하기 전에는 회원 DB를 바꾸지 않습니다.
- 과거 점검기록은 명부 갱신과 독립적으로 보존합니다.

## 주의

이 ZIP은 Railway/GitHub에 올릴 수 있는 실제 Phase 1 개발본이지만, 운영 배포 전에는 반드시 실제 PostgreSQL에서 동시성/부하/보안 테스트를 추가로 수행해야 합니다.

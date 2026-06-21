# FIRE 자산운용 백테스트 앱

2026년 6월 15일부터 본인과 아내가 FIRE를 시작했다고 가정하고, 같은 투자전략을 각자 독립적으로 적용했을 때 자산 흐름을 시뮬레이션하는 Next.js 앱입니다.

추가로 실제 운영을 위해 Streamlit, Supabase, GitHub Actions 기반의 인터넷 웹앱 구성을 포함합니다. 이 구성은 매일 TQQQ, QLD, SPYM, BOXX 종가와 USD/KRW 환율을 Supabase에 저장하고, Streamlit 웹앱에서 최신 데이터로 시뮬레이션을 갱신하는 흐름입니다.

## 운영 구조

```text
GitHub Actions
  -> scripts/collect_market_data.py
  -> yfinance에서 TQQQ, QLD, SPYM, BOXX, USD/KRW 조회
  -> Supabase market_prices, exchange_rates에 upsert
  -> Streamlit 앱이 Supabase에서 읽어 최신 시뮬레이션 표시
```

## Streamlit 실행

로컬에서 실행:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

환경변수는 `.env.example`을 복사해 `.env`로 만든 뒤 입력합니다.

```text
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key
```

Streamlit Cloud에 배포할 때는 앱의 Secrets에 같은 값을 넣습니다.

## 매일 자동 종가 수집

GitHub Actions 워크플로는 [.github/workflows/daily-market-data.yml](.github/workflows/daily-market-data.yml)에 있습니다.

기본 실행 시간:

```text
월~금 22:30 UTC
한국시간 기준 다음날 07:30 KST 전후
```

미국 정규장 마감 이후 데이터를 가져오기 위한 설정입니다. 수동 실행도 가능합니다.

GitHub 저장소 Secrets에 아래 값을 등록해야 합니다.

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

수동으로 데이터 수집:

```bash
python scripts/collect_market_data.py --start 2026-06-15
```

## Supabase 설정

Supabase SQL Editor에서 [supabase/schema.sql](supabase/schema.sql)을 실행합니다.

생성되는 주요 테이블:

- `market_prices`: 종목별 일별 종가
- `exchange_rates`: USD/KRW 환율
- `simulation_snapshots`: 향후 시뮬레이션 결과 저장용

현재 앱은 `market_prices`, `exchange_rates`를 읽어 화면에서 시뮬레이션을 계산합니다. 결과 스냅샷 저장은 다음 단계에서 연결합니다.

## 매월 인출일

현재 설정은 매월 15일입니다.

```text
MONTHLY_WITHDRAWAL_DAY = 15
MONTHLY_WITHDRAWAL_WON = 3,000,000
```

설정 위치는 [fire_simul/config.py](fire_simul/config.py)입니다.

주의: Python Streamlit 초안은 거래일 데이터 기반으로 동작합니다. 15일이 휴장일인 경우 달력일 기준 인출을 완전히 반영하려면 다음 단계에서 달력일 루프를 추가해야 합니다.

## 모바일에서 확인

인터넷 웹앱으로 확인하는 가장 쉬운 방법은 Streamlit Cloud 배포입니다.

1. 이 폴더를 GitHub 저장소로 push
2. Supabase 프로젝트 생성
3. Supabase SQL Editor에서 `supabase/schema.sql` 실행
4. GitHub Secrets에 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` 추가
5. GitHub Actions의 `Daily market data`를 수동 실행해 초기 데이터 저장
6. Streamlit Cloud에서 GitHub 저장소 연결
7. Main file path를 `streamlit_app.py`로 지정
8. Streamlit Secrets에 `SUPABASE_URL`, `SUPABASE_ANON_KEY` 입력
9. 배포된 URL을 휴대폰 브라우저에서 열기

이렇게 배포하면 PC를 켜두지 않아도 휴대폰에서 항상 최신 시뮬레이션을 볼 수 있습니다.

## Next.js 개발 실행

기존 Next.js 초안 실행:

```bash
pnpm install
pnpm dev
```

테스트:

```bash
pnpm typecheck
pnpm test
```

## 프로젝트 구조

```text
streamlit_app.py                     Streamlit 인터넷 웹앱
scripts/collect_market_data.py       매일 종가 수집 스크립트
supabase/schema.sql                  Supabase 테이블 및 RLS 정책
fire_simul                           Python 데이터 수집/시뮬레이션 모듈
.github/workflows                    GitHub Actions 자동 실행
src/app                              Next.js 화면, 스타일, 앱 진입점
src/components                       Next.js 대시보드 UI 컴포넌트
src/lib/strategy                     TypeScript 전략 타입, 샘플 데이터, 백테스트 엔진
src/lib/utils                        금액/날짜 표시 도우미
```

## 데이터 모델 설계

개인 포트폴리오는 본인과 아내가 완전히 분리된 상태로 계산됩니다.

- 자산: TQQQ, QLD, QLD 대기현금, SPYM, BOXX
- 상태: TQQQ 200일선 전략 상태, QLD 운용주기, 생활비 인출 누계
- 기록: 거래내역, 일별 스냅샷, 결과지표
- 부부 합산값은 비교와 대시보드 표시용으로만 계산합니다.

## 구현 계획

### 1단계

- Next.js, React, TypeScript, Tailwind CSS, Recharts, Vitest 구성
- 시나리오 선택: 부부 합산 9억, 12억, 15억
- 본인·아내 초기자산 입력
- 개인별 QLD 2,000만 원 고정 시작
- 합계가 시나리오 금액과 다르면 경고 표시
- 기본 대시보드와 샘플 백테스트 결과 표시

### 2단계

- 시장데이터 모델과 샘플 데이터
- TQQQ 200일선 상향 돌파, 하향 이탈
- 3거래일 분할매수
- 진입 유효·무효 판정
- TQQQ 매도금은 BOXX, QLD 매도금은 QLD 대기현금 이동

### 3단계

- QLD 연초 추가매수
- QLD 누적 정기투입원금 8,000만 원 한도
- QLD 평가액 8,500만 원 이상 정산
- QLD 초과분 TQQQ 이동 및 주기 반복

### 4단계

- BOXX 하한 1억 원 또는 3,600만 원
- 성장·방어 3:1 리밸런싱
- 월 300만 원 생활비 인출
- 거래내역과 일별 스냅샷 저장

### 5단계

- 9억·12억·15억 시나리오 비교
- 총자산, 자산별 평가액, 200일선, BOXX 하한, QLD 주기 그래프
- 최대낙폭, 인출 성공률, 자산 고갈일 등 결과통계
- CSV 내보내기

### 6단계

- 단위테스트와 통합테스트 확대
- 실제 데이터 수집 또는 CSV 업로드 연결
- 배포 설정

## 현재 구현 범위

이 첫 버전은 실행 가능한 앱과 전략 엔진의 핵심 규칙을 포함합니다.

- 본인·아내 독립 포트폴리오
- 시작일 2026-06-15
- QLD 개인별 2,000만 원 초기값
- TQQQ 200일선 상향·하향 신호
- 3일 분할매수와 진입 유효성 판정
- QLD 연초 추가매수와 정산
- BOXX 하한 계산
- 생활비 인출 실패 기록
- 샘플 데이터 기반 대시보드와 그래프
- 주요 전략 함수 테스트

## TODO

- Python Streamlit 시뮬레이션은 실제 데이터 연결용 초안입니다. TypeScript 엔진에 구현된 3일 분할매수, 진입 유효성 판정, 거래내역 저장을 Python 경로에도 동일하게 확장해야 합니다.
- 환율은 저장하지만 현재 Streamlit 시뮬레이션은 원화 초기자산을 가격 변화율로 평가합니다. 실제 USD 매수 수량 기반 계산으로 바꾸려면 원화-달러 환산 정책을 확정해야 합니다.
- 휴장일인 생활비 인출일을 달력일 기준으로 처리하는 규칙은 다음 단계에서 달력일 루프로 확장해야 합니다.

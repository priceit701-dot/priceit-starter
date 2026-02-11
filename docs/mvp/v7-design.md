# MVP v7 - 운영 대시보드 디자인 완성도 개선

## 범위
- 대상: `web/dashboard.html` (기존 `/dashboard` 엔드포인트가 서빙하는 단일 페이지)
- 목표: 운영자가 실제 모니터링 상황에서 **빠르게 읽고 즉시 판단**할 수 있도록 정보 구조/문구/상태 표현을 개선.

## 변경점 요약

### 1) 정보 구조 재설계 (KPI → 분포 → 이벤트 피드)
- 상단 헤더에 운영 컨텍스트를 명확히 배치:
  - 자동 갱신 주기
  - 마지막 갱신 시각
  - 수집 상태 배지(정상/로딩/API 오류)
- 핵심 KPI 4개를 1열 묶음으로 정리:
  - 누적 수집 메시지
  - 누적 이벤트
  - 최근 메시지 시각
  - 24시간 스킵 합계(+감시 상태)
- 중단 영역은 운영 판단에 바로 쓰는 분포 3종으로 구성:
  - 이벤트 유형 분포
  - 상위 룸 메시지 분포
  - 24시간 스킵 사유
- 하단은 최근 이벤트 피드 + 운영 체크포인트(정상/주의/점검 필요)로 구성.

### 2) 가독성/디자인 일관성 개선
- 다크 관제형 UI로 통일 (색상 토큰 기반): 배경/패널/테두리/강조색/상태색 일관화.
- 카드/패널/테이블 반경, 간격, 타이포(숫자·모노스페이스 포함) 통일.
- 수치 비교가 쉬운 형태로 개선:
  - 분포 테이블에 비율 바(bar) 추가
  - 숫자 컬럼 우측 정렬 및 tabular 숫자 폰트 사용
- 운영 문구 한국어 통일:
  - 기존 영문/혼합 표기 제거
  - 상태 문구를 운영 문맥(모니터링/품질 확인/장애 대응)으로 정리.

### 3) 반응형 개선 (모바일/데스크톱)
- 데스크톱(12-column grid): KPI 4열 + 분석/피드 분할.
- 태블릿 이하: KPI 2열.
- 모바일: KPI/패널 전부 1열 스택으로 재배치.
- 테이블은 패널 내부 스크롤로 처리해 화면 깨짐 방지.

### 4) 로딩/빈상태/오류 상태 명확화
- API 요청 전: 패널별 로딩 상태 메시지 표시.
- 데이터 없음: 패널별 빈상태 문구 표시.
- API 오류: 패널별 오류 상태 박스 + 상단 상태 배지를 `API 오류`로 전환.
- 기존 API 경로/기능(` /stats/summary`, `/stats/quality`, `/events/recent`)은 유지.

## 구현 상세
- 파일: `web/dashboard.html`
- 주요 구현 포인트:
  - `load()`에서 `Promise.all`로 3개 API 동시 조회 유지
  - 상태 제어 유틸 분리: `setHealth`, `setState`
  - 분포 렌더링 공통화: `renderDist`, `renderSkips`, `renderFeed`
  - XSS 방어용 `escapeHtml` 적용
  - 이벤트 타입 톤 분리(`PRICE_DOWN/RESTOCK` 계열 vs `PRICE_UP/SOLD_OUT` 계열)

## 검증 (실행 근거만 기록)

### A. 스모크 테스트
실행:
```bash
python3 scripts/verify_v3.py
```
결과:
```text
V3_STATUS quality= 200 recent= 200 summary= 200
V3_COUNTS event_quality= 9 skip_reasons= 0
V3_COUNTS recent_items= 5 messages= 37694 events= 1840
```

추가 확인:
```bash
curl -sSf http://127.0.0.1:8879/stats/summary
```
파싱 결과:
```text
messages 37694 events 1840
```

### B. 화면 검증 (스크린샷)
- 데스크톱(리사이즈 1512x982) 캡처:
  - `MEDIA:/Users/sanghun/.openclaw/media/browser/2ef7306c-89c3-4281-97c8-e6ae2f11aa63.png`
- 모바일(리사이즈 390x844) 캡처:
  - `MEDIA:/Users/sanghun/.openclaw/media/browser/f3d730b0-222f-4bb1-9424-d36fef793cf6.jpg`

## 리스크/한계
- 데이터 볼륨이 많은 룸 분포는 모바일에서 세로 길이가 길어질 수 있음(현재는 패널 내부 스크롤로 완화).
- `/stats/quality`의 `event_quality`를 아직 별도 시각화하지 않았고, `skip_reasons` 중심으로 표현함.
- 성능 측정(렌더링 FPS, 매우 대량 데이터)은 본 변경에서 별도 벤치마크하지 않음.

## 다음 개선 제안
1. `event_quality`(유형별 평균 confidence) 카드/히트맵 추가.
2. 룸 검색/필터(Top N, 룸명 검색) 제공.
3. 이벤트 피드에 가격 변동값(old/new) 강조 표시.
4. 상태 배지를 수집기/알림기 등 컴포넌트별 헬스체크와 연동.

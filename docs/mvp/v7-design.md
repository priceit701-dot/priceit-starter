# MVP v7 Dashboard Design Variants (5안)

작성일: 2026-02-12

## 범위
- `web/dashboard_v1.html` ~ `web/dashboard_v5.html` 신규 추가
- `web/dashboard.html`를 버전 선택 런처로 변경
- 공통 API 유지
  - `/stats/summary`
  - `/stats/quality?limit_hours=24`
  - `/events/recent?limit=20`

## 버전별 특징

### v1: 미니멀 운영형 (`dashboard_v1.html`)
- 단순 카드 3개(메시지/이벤트/마지막 메시지)
- 4개 표(이벤트 유형, 상위 룸, 스킵 사유, 최근 이벤트)
- 최소 스타일, 운영 체크에 집중

### v2: KPI 카드 중심형 (`dashboard_v2.html`)
- KPI 카드 4개(스킵 총합 포함)
- 리스트 기반 정보 구조(최근 이벤트, 유형 분포, 룸, 스킵)
- 카드 중심 UI로 빠른 상황 판단

### v3: 테이블/분석형 (`dashboard_v3.html`)
- 최근 이벤트를 분석 테이블 중심으로 배치
- 우측 패널에 요약/집계 표 배치
- 모노스페이스 폰트 기반의 분석 친화 스타일

### v4: 타임라인 모니터링형 (`dashboard_v4.html`)
- 최근 이벤트를 타임라인 카드로 구성
- 상단에 운영 요약 + 이벤트 유형 + 스킵/룸 혼합 요약
- 이벤트 흐름 관찰 중심

### v5: 다크모드 관제형 (`dashboard_v5.html`)
- 다크 테마 기반 관제실 스타일
- 이벤트 스트림 + 우측 분석 패널(유형/룸/스킵)
- 시스템 상태(NORMAL/ERROR) 시각화

## 공통 기능(전 버전)
- 7초 주기 자동 갱신 (`setInterval(load, 7000)`)
- 로딩 상태: `로딩 중...`
- 빈 상태: `데이터 없음` 또는 각 섹션의 빈 상태 문구
- 오류 상태: `오류: ...` 메시지 및 최소 대체 UI 표시
- 반응형: `@media` 기반 1열/2열 전환

## 사용 시나리오
- 운영 담당자가 `web/dashboard.html`에서 상황에 맞는 뷰 선택
  - 빠른 점검: v1
  - KPI 중심 보고: v2
  - 상세 분석: v3
  - 이벤트 흐름 모니터링: v4
  - 야간/관제 화면: v5

## 검증 결과 (실제 확인한 항목만 기재)
1. 파일 생성 확인
   - `web/dashboard_v1.html` ~ `web/dashboard_v5.html` 존재
2. 런처 링크 확인
   - `web/dashboard.html`에 `dashboard_v1.html`~`dashboard_v5.html` 링크 존재
3. 공통 API 사용 확인
   - 5개 버전 모두 동일 3개 엔드포인트 문자열 포함
4. 상태 처리 코드 확인
   - 5개 버전 모두 로딩/빈상태/오류 처리 문구 및 렌더 분기 존재

> 참고: 본 문서의 검증 결과는 코드/정적 확인 기준이며, 서버 실데이터 응답 검증은 별도 실행 환경에서 추가 확인 필요.

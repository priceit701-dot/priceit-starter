# v10 Seller Content Focus

## 변경 목적
사용자 피드백("이벤트보다 이벤트 내용이 중요") 반영.
셀러가 즉시 조치 가능한 정보 중심으로 셀러 어드민을 재설계했다.

## Before → After 요약

### Before (v9)
- 이벤트 타입 중심 카드/테이블 노출
- 최근 알람 피드 비중이 높음
- 셀러가 "무엇을 어떻게 조치해야 하는지"를 직접 해석해야 함

### After (v10)
- 화면 구조를 의사결정 질문 중심으로 재배치
  1) 지금 당장 할 일 Top N
  2) 가격/품절/지연 핵심 내용 요약
  3) 상품별 변경 내용(문장형)
  4) 권장 액션
  5) 알람유형 7종은 보조지표로 유지
- API에 셀러 인사이트 필드 추가(기존 필드 호환 유지)
  - `action_priority_list`
  - `change_summary_by_item`
  - `stock_risk_items`
  - `recommended_actions`
  - `evidence_fields`

## 구현 상세

### 1) 정보모델 문서
- `docs/plan/seller-needs-model.md`
- 셀러 질문 기반으로 필요한 데이터 항목을 정의

### 2) API 확장 (`GET /stats/seller`)
- 기존 응답 필드 유지:
  - `today_alert_summary`, `recent_alert_feed`, `action_required_items` 등
- 신규 인사이트 필드 추가:
  - 우선순위 액션 리스트 + 근거(evidence)
  - 상품 단위 변경 요약(빈도/변동폭/최근시각)
  - 품절/지연 리스크 리스트
  - 권장 액션 텍스트
  - 윈도우/카운트 근거 메타

### 3) 프론트 개편 (`web/admin_seller.html`)
- 이벤트 raw 테이블 중심 구성 축소
- Top N/핵심 요약/상품별 문장/권장 액션 중심 UI로 교체
- 7종 알람은 하단 보조 지표로 이동

## 검증

### API 200 + 신규 필드 확인
- `GET /stats/seller?limit_hours=24&feed_limit=30&action_limit=10`
- 결과: HTTP 200
- 확인 필드:
  - `action_priority_list` ✅
  - `change_summary_by_item` ✅
  - `stock_risk_items` ✅
  - `recommended_actions` ✅
  - `evidence_fields` ✅

### 실제 렌더링 확인
- `GET /admin/seller` HTML에 신규 섹션/렌더링 대상 id 존재 확인
  - `topActions`, `headlineKpi`, `changeRows`, `recommendRows`, `summary` ✅
- 프론트 JS가 신규 필드를 fetch 후 렌더링하도록 반영 ✅

## 변경 파일
- `src/api.py`
- `web/admin_seller.html`
- `docs/plan/seller-needs-model.md`
- `docs/mvp/v10-seller-content-focus.md`

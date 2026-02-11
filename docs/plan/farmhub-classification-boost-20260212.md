# 팜허브/최고집 상품명 분류율 추가 강화 계획 (2026-02-12)

## 목표
- 미분류(`미분류 상품`) 비율을 추가로 낮춘다.
- 공지/안내 문구가 상품명으로 노출되는 오분류를 억제한다.
- 적용 범위: 최고집 + 팜허브 룸 중심 seller insight 라벨링 경로(`src/api.py`).

## 개선 포인트

### 1) room context 상속 고도화 (직전 1건 → 최근 N건)
- 기존: 룸별 마지막 1개 상품명만 상속.
- 변경: 룸별 최근 `ROOM_CONTEXT_WINDOW=5`개 명시 상품 후보를 deque로 유지.
- 상속 대상 이벤트: `SOLD_OUT, DELAY_NOTICE, NOTICE, PRICE_UP, PRICE_DOWN, RESTOCK`.
- 기대효과: 공지형 메시지 연속 구간에서 `미분류 상품` 감소.

### 2) 공지형 헤더/이모지/상태어 강한 차단
- `NOTICE_BLOCK_PATTERNS` 추가:
  - `#📢📌🔔🚨⚠️... + 공지/안내/알림/배송/출고/발주`
  - `필독/마감/전달사항/출고안내` 등
- `_looks_like_notice_header()`로 헤더성 문구 감지 후 상품명 후보 차단.
- `_is_noise_item_name()`에서 notice-header 직접 배제.

### 3) seller catalog normalize 매칭 강화
- 카탈로그(`seller_product_catalog_20260212.json`)에서
  - `base_name_top100`
  - `keywords` 정제(브라켓/괄호/중량/등급 불용어 제거)
  를 합쳐 `CATALOG_ITEM_CANDIDATES` 구성.
- normalize 매핑(`_CATALOG_ITEM_NORM_MAP`)으로 메시지와 공백/기호 무시 매칭.
- 기존 term-map/일반 keyword 매칭 사이에 catalog 매칭 단계 추가.

### 4) 팜허브 빈출 문구 템플릿 매핑
- `_extract_template_item_from_text()` 추가.
- 패턴:
  - `... [상품] 입고/재입고/출고/품절`
  - `... [상품] 가격변동/가격인상/가격인하`
- status 토큰 포함 후보/노이즈 후보는 배제.
- context 상속 전에 템플릿 후보를 우선 사용.

## 검증 계획
1. 최근 7일, 최고집+팜허브 이벤트 샘플에서 before/after 비교
2. 지표
   - 미분류 건수/비율
   - 공지문구 오분류 사례 수
3. 산출물
   - `reports/farmhub_classification_boost_eval_20260212.md`

## 반영 파일
- `src/api.py`
- `reports/farmhub_classification_boost_eval_20260212.md`

## 실행 근거(검증 커맨드)
- 데이터 확인: sqlite query (최근 7일, 최고집+팜허브)
- 문법 점검: `python3 -m py_compile src/api.py`
- 평가 생성: ad-hoc python 실행으로 before/after 리포트 산출

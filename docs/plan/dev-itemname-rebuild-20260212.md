# dev-itemname-rebuild-20260212

## 1) 현재 문제 정리
- 상태값/노이즈(긴급공지, 품절, 안내, 발주 등) 단어가 상품명보다 먼저 잡혀 `item_name`이 불명확해짐.
- 동일 상품이 표기 흔들림(띄어쓰기, 별칭, 오타)으로 분산되어 집계/검색 품질 저하.
- 중량/등급/산지/포장/보관 정보가 상품명 본문에 섞여 있어 재구성(표시명 생성, 옵션 필터링) 어려움.
- API 레이어는 `product_name` 공백 시 단순 문자열 절단 fallback만 사용하여 미분류가 증가.

## 2) 개선 설계 (추출 -> 정규화 -> 별칭치환 -> 옵션분리 -> 최종표시)
1. **추출(Extract)**
   - 따옴표 상품명, 브라켓 내 상품명 후보 우선.
   - 공지/품절/지연 등 상태어 브라켓은 제거하고 본문에서 상품명 후보 추출.
2. **정규화(Normalize)**
   - 공백/특수문자 정리, 가격/URL/헤더성 토큰 제거.
3. **별칭치환(Alias Replace)**
   - `data/vendor_aliases.json::__item_aliases__` 기반 문자열 치환으로 표준명 수렴.
4. **옵션분리(Option Split)**
   - 정규식 기반 옵션 토큰 추출: 중량/등급/산지/포장/보관.
   - 옵션 토큰 제거 후 핵심 상품명(`item_name_norm`) 생성.
5. **최종표시(Final Display)**
   - 우선순위: `product_name` -> `item_name_norm` -> `item_name_raw` -> vendor -> `미분류 상품`.
   - API 응답에 item profile 필드 동봉해 UI/리포트에서 재구성 가능하게 함.

## 3) 필드 정의
- `item_name_raw`: 원문에서 추출한 상품명 후보(노이즈 제거 후, 옵션 포함 가능).
- `item_name_norm`: 별칭치환/옵션 분리 적용 후의 정규화 상품명.
- `option_tokens`: 추출된 옵션 토큰 배열(예: `A급`, `2kg`, `국산`, `냉장`, `박스`).
- `brand`: 벤더 또는 본문 내 브랜드 후보.
- `grade`: 등급 토큰(예: `특`, `A급`, `특품`).
- `origin`: 산지/원산지 토큰(예: `남해`, `국산`, `제주`).
- `unit`: 중량/규격 토큰(예: `2kg`, `500g`, `10입`).

## 4) 코드 반영 범위
- `src/parser.py`
  - `extract_item_profile()` 추가.
  - 상태어/공지 노이즈 분리 강화.
  - 옵션 토큰 추출 로직 보강.
  - parse 시 `product_name`에 `item_name_norm` 우선 반영.
- `src/api.py`
  - `_extract_item_fields()` 추가.
  - seller stats feed/action 응답에 item profile 필드 포함.
- `data/vendor_aliases.json`
  - `__item_aliases__` 섹션 추가(상품 별칭 정규화용).

## 5) 리스크/후속
- 정규식 기반 추출은 문장 패턴 변화에 민감하므로 주간 샘플 회귀 점검 필요.
- DB schema 확장 없이 API 계층에서 profile 생성하므로, 장기적으로는 events/item_profile 저장 테이블 분리 검토.

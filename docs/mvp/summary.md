# MVP 1→5 종합 리포트

## 버전별 성과
- **v1 (정합성/중복 안정화)**
  - `ingestion_audit` 도입, 10분 윈도우 중복 차단, 메시지 해시 개선.
  - 검증 수치: `messages=37367`, `events=1513`, `exact_duplicate_keys=0`.
- **v2 (파서 정확도 개선)**
  - 지연 공지/재입고 오인식 감소, 상품명 정제 보강, 회귀테스트 4건 추가.
  - 샘플 벤치마크: F1 `0.7826 → 1.0` (20샘플 기준).
- **v3 (API/대시보드 확장)**
  - `/stats/quality`, `/events/recent` 추가.
  - 대시보드에서 스킵 사유/최근 이벤트 실시간 표시.
- **v4 (자동화 컨트롤러 실동작 강화)**
  - `NEXT_STEP_OK`, `EVIDENCE:` 토큰 JSON 검증 실제 적용.
  - 실패 코드 세분화 + retry/recovery 훅 연결.
- **v5 (운영 시뮬레이션/릴리즈 후보화)**
  - runbook 검증 스크립트로 v1~v4 연속 확인.
  - 출력 토큰을 controller 정책과 직접 호환.

## 남은 블로커
1. 실제 카카오 UI 자동수집(포커스/권한/앱 업데이트 영향) E2E 자동화 미완.
2. 텔레그램 알림 실패 재시도/백오프 정책 부재.
3. 대량 트래픽 성능 한계(현재 SQLite 단일노드) 검증 필요.

## 즉시 운영 가능한 범위
- 로컬/단일 인스턴스 기준:
  - 수집 → 파싱 → 이벤트 저장 → 핵심 알림(PRICE_UP/DOWN/SOLD_OUT/RESTOCK) → 대시보드 모니터링.
- 운영 전 권장:
  - `executor_command`, `recovery_command` 정책값 채우고 `simulate_ops_runbook.py` PASS 확인.
  - 카카오 자동수집기 실제 장비에서 1일 burn-in 테스트.

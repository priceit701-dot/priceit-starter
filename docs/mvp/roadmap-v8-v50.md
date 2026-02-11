# MVP Roadmap v8 ~ v50

## 연결 컨텍스트 (v1~v7)
- v1~v5: 수집/파싱/API/controller 기본 운영 루프와 검증 체계 정립 (`docs/mvp/v1.md`~`v5.md`, `summary.md`)
- v6: 알림 idempotency/retry, controller evidence 엄격화, 로컬 부하 점검 (`docs/mvp/v6.md`)
- v7: 운영 대시보드 UX/가독성 개선 (`docs/mvp/v7-design.md`)
- **v8부터는 "운영 품질 자동검증(qa loop) + 장기 버전 거버넌스"를 기준으로 확장**

---

## v8~v50 운영 프레임

### 단계 A: 품질 기반 고정 (v8~v12)
- v8: QA foundation + 실행 증거 표준화
- v9: 수집기 실기기 burn-in 자동 체크
- v10: API 회귀셋 확대/계약테스트
- v11: 알림 채널 다중화/장애 fallback
- v12: 대시보드 데이터 무결성 자동 감사

### 단계 B: 안정화/관측성 (v13~v20)
- 에러 budget, SLO, 알림 폭주 제어
- 로그 회전/보존정책, 장애 리플레이 툴링
- 운영 runbook 자동 권고

### 단계 C: 성능/규모 확장 (v21~v30)
- SQLite 한계점 대응(파티셔닝 또는 외부 DB 이전 준비)
- 고빈도 수집 부하 대응
- parser rule + 통계 혼합 검증

### 단계 D: 운영 자동화 고도화 (v31~v40)
- controller policy 시뮬레이션 자동화
- 배포/롤백 기준 정량화
- 멀티 환경(로컬/스테이징/운영) QA 파이프라인

### 단계 E: 제품화/거버넌스 (v41~v50)
- 릴리즈 승인 게이트 정식화
- 규정 준수(감사 로그/변경 추적) 강화
- 운영/분석용 문서 자동 생성 및 추적

---

## 버전 인덱스 (v8~v50)
아래 상세 상태는 `docs/mvp/version_status.json`에서 단일 소스로 관리.

| Range | Focus | Exit Criteria |
|---|---|---|
| v8~v12 | QA/신뢰성 기초 | 자동 QA가 릴리즈 체크리스트를 대체 가능 |
| v13~v20 | 관측성/안정화 | 장애 감지→원인 추적 시간을 유의미하게 단축 |
| v21~v30 | 확장성 | 수집량 증가에도 SLA 내 처리 |
| v31~v40 | 자동운영 | 정책 기반 운영 개입 최소화 |
| v41~v50 | 제품화 완성 | 감사/승인/배포 근거 자동 추적 |

---

## 운영 규칙
1. 각 버전은 PLANNED/IN_PROGRESS/DONE/BLOCKED 중 하나만 가진다.
2. DONE 전환 조건: 실행 근거(로그/요약/리포트)가 문서와 함께 존재해야 한다.
3. BLOCKED는 원인/재현/다음 조치가 `owner_notes` 또는 별도 보고서에 남아야 한다.
4. v1~v7 학습사항(중복방지, evidence 규약, dashboard 관측성)은 v8+ 설계에서 후퇴 금지.

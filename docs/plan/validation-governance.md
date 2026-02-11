# Validation Governance: Duplicate Cleanup Approval Loop

작성일: 2026-02-12
적용 대상: `messages`, `events`, `products`, `알람요약(v_events_alarm 기반 집계)`

## 1) 프로세스 (기획 검증 -> 반영 승인 -> 적용 -> 사후검증)

1. **기획 검증 (Plan Validation)**
   - 중복 정의를 문서/스크립트에 명시한다.
   - `scripts/dedup_audit.py`로 사전 수치 증거를 확보한다.
   - 산출물: `reports/dedup_audit_YYYYMMDD.json`, `.md`

2. **반영 승인 (Approval Gate)**
   - 아래 승인 게이트를 모두 충족해야 적용 가능:
     - `DUPLICATE_OK`: 중복 정의/대상/삭제 기준이 검토되어 승인됨
     - `EVIDENCE`: 사전 리포트(pre 수치)와 롤백 경로가 첨부됨

3. **적용 (Apply)**
   - `--apply` 모드로 실행하되, 삭제 대상이 있을 때만 백업 후 적용한다.
   - 적용 전 백업 생성 규칙:
     - `data/priceit.db.backup_dedup_YYYYMMDD_HHMMSS`
   - 적용 원칙:
     - 동일 키 그룹에서 `id`가 가장 작은 1건 유지, 나머지 제거
     - 알람요약은 원천(`events`) 정리 결과를 통해 간접 보정

4. **사후검증 (Post Validation)**
   - 동일 스크립트 결과에서 `pre`/`post` 비교
   - 중복 건수(그룹/행) 감소 확인
   - 알람유형 집계 변화(타입별 delta) 확인

---

## 2) 승인 게이트 체크리스트

- [ ] `DUPLICATE_OK`: 아래 정의로 중복 판단하는 것에 동의
  - messages: `(room_name, sender, message_text, created_at)`
  - events: `(message_id, event_type, vendor, product_name, created_at)`
  - products: `(canonical_key)`
  - alarm_summary: `(room_name, event_type_std, vendor_std, product_std, created_at, message_id)`
- [ ] `EVIDENCE`: `reports/dedup_audit_YYYYMMDD.json/.md` 첨부
- [ ] `ROLLBACK_READY`: 백업 경로 및 복구 명령 확보

---

## 3) 실행 명령

```bash
# 사전 점검 (기본: audit only)
python3 scripts/dedup_audit.py --db data/priceit.db

# 승인 후 적용 (중복이 있을 때만 백업 + 반영)
python3 scripts/dedup_audit.py --db data/priceit.db --apply
```

---

## 4) 롤백

적용 시 JSON 리포트의 `backup_file`, `rollback.restore_command`를 단일 근거로 사용한다.

예시:
```bash
cp 'data/priceit.db.backup_dedup_YYYYMMDD_HHMMSS' 'data/priceit.db'
```

---

## 5) 보고 원칙

- 과장 금지: 수치/파일 근거가 없는 서술 금지
- 전/후 비교를 기본 단위로 보고
- 영향 범위는 `알람유형 집계(delta)`로 명시

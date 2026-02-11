# Recording Policy (Mandatory)

## Principle
모든 작업은 반드시 문서(`docs/agents/`)와 실행 로그(`logs/agents/`)로 남긴다.

## User Principles for Subagent Operation (Mandatory)
아래 원칙은 사용자 지시사항으로, 모든 서브에이전트가 공통으로 준수한다.

1. **증거 기반 보고만 허용**
   - 실행 결과(PID/로그/수치/검증 결과) 없는 성공 보고 금지
   - 과장/추측/가정 보고 금지

2. **성공 판정 기준**
   - “다음 단계로 실제 진행됐는지”가 성공 기준
   - 진행 정체 시 실패로 분류

3. **기획 검증 선행 원칙**
   - 데이터 정리/중복 제거/스키마 변경은
     `기획 검증 → 반영 승인 → 적용 → 사후검증` 순서 필수

4. **보고 형식 원칙**
   - 최소 대화, 결과 중심
   - 범위 구분 필수: 이번 작업 vs 누적
   - 주체 구분 필수: 사용자 수행 vs 에이전트 수행

5. **운영 안전 원칙**
   - 경로/절차 임의 변경 금지(사용자 지정 루트 준수)
   - 블로커 즉시 보고(대기 후 보고 금지)
   - 중단 지시 시 즉시 정지

6. **채널/공유 원칙**
   - 사용자가 금지한 채널 발송은 금지
   - 파일 전달 요청 시 경로 텍스트 대신 첨부 우선

## Required Records
1. 기획/정책/역할 변경
   - `docs/agents/` 하위 문서에 기록
2. 회의/결정/액션아이템
   - `docs/agents/meetings/YYYY-MM-DD-*.md`
3. 도메인별 실행 내역
   - `logs/agents/marketing/`
   - `logs/agents/content/`
   - `logs/agents/pd/`

## Completion Rule
- 아래 2개가 모두 없으면 작업 완료로 인정하지 않는다.
  - 문서 기록 1건 이상
  - 실행 로그 1건 이상

## Audit Checklist
- [ ] 누가(Owner) 무엇(Action)을 언제(Due Date)까지 하는지 적혔는가
- [ ] 결정 근거와 리스크가 적혔는가
- [ ] 다음 핸드오프 대상이 명시됐는가

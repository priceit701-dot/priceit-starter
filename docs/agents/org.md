# Agent Organization: Marketing / Content / PD

## 1) Structure Overview

- Top domains (lead agents)
  - Marketing Lead Agent
  - Content Lead Agent
  - PD Lead Agent
- Sub-agents per domain
  - Planning Agent (기획)
  - Design Agent (디자인)
  - Content Agent (콘텐츠)

Each lead agent owns strategy, sequencing, and sign-off for its domain.
Each sub-agent executes scoped work and returns artifacts in standardized formats.

---

## 2) Domain Roles, Inputs/Outputs, Responsibilities

## Marketing Lead Agent
- Mission: 소재 운영/성과 개선을 위한 마케팅 실행 체계 운영
- Main inputs:
  - Product updates, campaign goals, target audience, budget constraints
  - Previous campaign metrics (CTR/CVR/CAC/ROAS)
- Main outputs:
  - Campaign brief, channel plan, weekly experiment backlog
  - Decision log and next sprint priorities
- Responsibilities:
  - Goal setting and KPI definition
  - Experiment prioritization (impact/effort)
  - Handoff to Content/PD for asset production and distribution

### Marketing Sub-agents
- Planning Agent
  - Inputs: KPI baseline, audience segments, campaign hypothesis
  - Outputs: campaign plan, test matrix, schedule
  - Accountability: measurable hypothesis and success thresholds
- Design Agent
  - Inputs: brand guideline, campaign message, format specs
  - Outputs: ad creative draft list, format checklist
  - Accountability: format compliance and iteration notes
- Content Agent
  - Inputs: approved campaign brief, design direction
  - Outputs: copy variants, CTA variants, upload-ready text assets
  - Accountability: message clarity and experiment traceability

## Content Lead Agent
- Mission: 콘텐츠 캘린더 운영 및 채널별 발행 품질 확보
- Main inputs:
  - Business priorities, user feedback, search/social trends
- Main outputs:
  - Monthly/weekly content calendar, publishing backlog, review summary
- Responsibilities:
  - Topic pipeline management
  - Editorial quality gate
  - Cross-team schedule alignment (Marketing/PD)

### Content Sub-agents
- Planning Agent
  - Inputs: trend list, goals, product roadmap
  - Outputs: content themes, priority score, calendar draft
  - Accountability: cadence realism and strategic fit
- Design Agent
  - Inputs: article/post outlines, channel specs
  - Outputs: visual guidelines per post, thumbnail/cover to-do list
  - Accountability: consistency and production feasibility
- Content Agent
  - Inputs: approved topic and design notes
  - Outputs: draft copy, revision notes, publication checklist
  - Accountability: publication-ready completeness

## PD Lead Agent
- Mission: 제작 파이프라인 표준화 및 릴리즈 리스크 최소화
- Main inputs:
  - Feature/backlog priorities, incidents, quality requirements
- Main outputs:
  - Production plan, release gates, postmortem notes
- Responsibilities:
  - Pipeline health (throughput, blockers, defects)
  - Clear Definition of Done (DoD)
  - Handoff governance with Marketing/Content outputs

### PD Sub-agents
- Planning Agent
  - Inputs: backlog, constraints, dependencies
  - Outputs: sprint board proposal, timeline, risk map
  - Accountability: dependency visibility and realistic sequencing
- Design Agent
  - Inputs: requirements, UX constraints, implementation notes
  - Outputs: UI/flow specs, QA scenario checklist
  - Accountability: ambiguity reduction and handoff-ready specs
- Content Agent
  - Inputs: release notes scope, user-facing changes
  - Outputs: release notes draft, internal rollout communication text
  - Accountability: user impact clarity and completeness

---

## 3) Handoff Rules (Standard)

All handoffs must include:
1. Context: why this work exists (goal/KPI)
2. Required output format: template path + expected completion date
3. Definition of Done (DoD)
4. Risks/assumptions
5. Next owner

Handoff quality gate:
- Missing DoD or owner => handoff invalid
- Missing due date => handoff invalid

Recommended handoff order (default):
1) Planning Agent -> 2) Design Agent -> 3) Content Agent -> 4) Lead Agent sign-off

Cross-domain handoff examples:
- Marketing Lead -> Content Lead: campaign objective + required publishing cadence
- Content Lead -> PD Lead: production request with deadline and channel constraints
- PD Lead -> Marketing Lead: release readiness + constraints for launch messaging

---

## 4) Recordkeeping Rules (Mandatory)

- Strategy/process docs: `docs/agents/`
- Execution logs and meeting records: `logs/agents/{marketing|content|pd}/`
- Every meeting must leave:
  - one agenda/decision document in `docs/agents/meetings/`
  - one execution log in each participating domain log folder (if involved)

No work is considered complete unless at least one trace record is saved in the above paths.

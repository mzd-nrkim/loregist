---
name: docs-manage
description: "{docs_root}/../etc/ 공통 문서(방화벽·인프라·운영 정보) 조회·갱신. docs-manager Agent에 위임. (임의 문서 추가는 add-docs, 미래 계획은 future-plan 사용)"
argument-hint: <domain> <action> [args...] [--project <key>] — firewall | infra | future | airflow
allowed-tools: Agent, Read
---

## 프로젝트 해석

1. `--project <key>` 인자가 있으면 그 프로젝트 사용
2. 없으면 `loregist project current` (cwd 기준 자동 추론)
3. 추론 실패 시 사용자에게 프로젝트 키 질문

공통 문서 위치: `{docs_root}/../etc/` (= `personal-work/projects/{project}/etc/`)

→ loregist/CLAUDE.md "스킬 공통 — 프로젝트 추론 규칙" 적용

> etc/ 고정 문서 전용 — 작업문서 추가(add-work), 임의 문서 수정(add-docs), 미래 계획(future-plan)은 별도 스킬 사용.

# 역할

`$ARGUMENTS`를 파싱하여 docs-manager Agent에 위임한다.

# 입력 → Agent 프롬프트 변환

| 입력 | Agent에 전달할 프롬프트 | 비고 |
|---|---|---|
| `firewall status` | "방화벽_이력.md를 읽고 경로별 O/⏳/X 현황을 요약해줘" | |
| `firewall update ServiceA ServiceB DEV O (05-02/05-08)` | "방화벽_이력에서 ServiceA→ServiceB 경로의 DEV 셀을 O (05-02/05-08)로 갱신해줘" | |
| `infra update "DB_서비스 SID 추가"` | "인프라_접속정보.md §3.3 DB_서비스 테이블에 SID를 갱신해줘" | |
| `future list` | "미래_계획.md를 읽고 주제별 미완료 건수와 선행 조건을 요약해줘" | `future-plan list`로 직접 호출 권장 |
| `future add "ServiceC 전 환경 연동"` | "미래_계획.md에 새 섹션 'ServiceC 전 환경 연동'을 추가해줘" | `future-plan add`로 직접 호출 권장 |
| `future promote "Project_A STG"` | "미래_계획.md에서 'Project_A STG/DEV' 섹션의 미완료 항목을 추출하고, 오늘 작업문서에 추가해줘" | `future-plan promote`로 직접 호출 권장 |
| `airflow update "POOL_RECYCLE node-02 적용"` | "운영_정보.md의 Connection Pool 설정 섹션에서 node-02 상태를 갱신해줘" | |
| `airflow status` | "운영_정보.md를 읽고 현재 노드·DAG·DB 설정 현황을 요약해줘" | |
| (없음) | "etc/ 전체 문서 상태를 요약해줘" | |
| 자연어 | 그대로 Agent 프롬프트에 전달 | |

# 처리

1. `$ARGUMENTS`를 파싱한다
2. 대화 맥락에서 추가 정보(고객 회신, 로그 분석 결과 등)가 있으면 프롬프트에 포함한다
3. docs-manager Agent를 호출한다
4. Agent 결과를 사용자에게 출력한다

# 제약 조건

1. 이 스킬은 Agent 래핑만 수행 — 직접 문서를 수정하지 않는다
2. `future promote`는 작업문서도 수정하므로 Agent의 `maxTurns`가 충분한지 확인

---
name: catalog-update
description: handbook 파일을 스캔하여 _wiki/T-xxx.md(topic) / D-xxx.md(decision) 파일을 자동 생성·갱신한다. --now로 즉시 전체 스캔, --force로 기존 본문 재생성, --all로 전 프로젝트 순회.
argument-hint: [--project <key>] [--all] [--now [이름]] [--force] [--recommend-sources] [--dry-run] [--scan] [--commit]
allowed-tools: Agent, Bash, Read, Write, Edit, Glob, Grep
---

## 프로젝트 해석

1. `--project <key>` 인자가 있으면 그 프로젝트 사용
2. 없으면 `loregist project current` (cwd 기준 자동 추론)
3. 추론 실패 시 사용자에게 프로젝트 키 질문

`docs_root`: 추론된 프로젝트의 docs_root 값 (`loregist project list`로 확인)

→ loregist/CLAUDE.md "스킬 공통 — 프로젝트 추론 규칙" 적용

이 스킬의 모든 상대 경로는 `{docs_root}/` 기준이다.

# 역할

`handbook`에 등록된 파일(또는 대체 소스)을 LLM이 분석하여 `_wiki/T-xxx.md`(topic) / `_wiki/D-xxx.md`(decision) 파일을 자동 생성·갱신한다.

# 트리거 키워드

- `catalog-update`, `카탈로그 업데이트`, `catalog update`
- `handbook 스캔`, `topic 추출`, `decision 추출`
- `카탈로그 생성`, `카탈로그 갱신`

# 인수 정의

| 인수 | 설명 |
|---|---|
| `--project <key>` | 대상 프로젝트 키 명시 (생략 시 자동 추론) |
| `--all` | 전 프로젝트 순회 — `loregist project list --json` 목록 전체에 대해 순차 실행 |
| `--now [이름]` | 즉시 전체 스캔 모드 — `.last_catalog_update` base 무시, 전체 스캔 강제 실행. `[이름]`을 지정하면 T-xxx/D-xxx id 또는 제목 매칭 항목만 처리. `--scan` 포섭: `--scan`과 동일한 스캔 경로를 수행하면서 게이트(base) 무시 + 누락 항목 생성까지 포함 |
| `--force` | 기존 T/D 항목 본문 재생성 포함 — 보호 장치 하 재작성 허용 (`--now` 또는 `--scan`과 함께 사용) |
| `--recommend-sources` | handbook 추천 모드 — 파일을 분석해 추가 여부를 사용자에게 확인 |
| `--dry-run` | 생성 예정 목록만 출력, 파일 작성·`.last_catalog_update` 갱신 건너뜀 |
| `--scan` | 코드·문서 직접 스캔 모드 — cold start나 drift 감지 시 사용. `--now` 없이 단독 사용 시 base 필터 적용. `--now`의 별칭 역할: `--scan` 단독 = 전체 스캔만, `--now`는 `--scan`을 포섭하여 게이트 무시+누락 생성까지 수행 |
| `--commit` | 완료 후 변경된 `_wiki/*.md` 파일을 git commit |
| `--defer-embed` | embed 단계를 스킵하고 `EMBED_FILES: <경로들>` 한 줄을 출력 — wiki-update 등 상위 오케스트레이터가 일괄 embed할 때 사용 |

> 인수 조합·3축 모드 매트릭스·대표 조합·`--now`와 `--scan` 관계 세부는 `references/modes.md` 참조 — 어떤 모드로 진입할지 판단할 때 읽는다.

# 모드 분기 (요약 흐름)

우선순위 순으로 분기한다. 세부 규칙은 `references/modes.md` 참조 — 각 모드의 동작 규칙을 확인할 때 읽는다.

1. `--recommend-sources` → **B-2** 실행 후 종료
2. `--all` → **B-3-all** 전 프로젝트 순회 (각 프로젝트에 3~5 적용)
3. `--now [이름]` → **B-1c** base 무시 전체 스캔 (`[이름]` 지정 시 필터)
4. `--scan` → **B-1b** 코드·문서 직접 스캔 (cold start·drift 감지)
5. 인자 없음 → **B-1a** 컨텍스트 기반 모드

`--force`는 독립 축 — 3~5 어느 모드와도 조합 가능.

스캔 후 공통 처리 흐름: **B-3a(handbook 스키마) → B-3(소스 결정) → B-4(LLM 분석) → B-5(중복 검사) → B-6(ID 부여) → B-7(파일 작성) → B-8(완료 처리)**

> 각 단계 세부 절차는 `references/processing.md` 참조 — 각 B-N 단계를 실행하기 직전에 읽는다.

> 출력 형식·`--all` 집계·연계 흐름 순서 예시는 `references/output.md` 참조 — 결과를 출력하거나 다른 스킬과 연계할 때 읽는다.

# 제약 조건

1. **기존 `_wiki/*.md` 파일 본문 덮어쓰기:**
   - `--force` 미지정: 본문 불변 — `related:` 업데이트만 허용 (기존 동작 유지)
   - `--force` 지정: B-5-force 보호 장치(status:edited 제외, LOCK 마커 보존, frontmatter 보존, 항목별 승인) 하 본문 재작성 허용
2. `--dry-run` 시 파일 Write 금지 — 출력만 (`--force`와 조합 시에도 동일)
3. `_wiki/` 디렉토리 내 파일은 recommend-sources 후보에서 제외
4. 중복 판정(유사도 > 0.85)된 항목은 신규 파일 생성하지 않음
5. ID 패딩은 항상 3자리 유지
6. handbook이 있으면 반드시 1순위만 사용 — 대체 소스와 혼합 금지
7. `projects.toml` 편집은 `--recommend-sources` 모드에서만 수행
8. **handbook 파일 수정 금지** — 이 스킬은 모든 handbook 항목을 읽기 전용으로만 사용한다. handbook 파일 갱신은 `/wiki-update` 스킬에서 수행한다
9. `--all` 순회 시 `_wiki/` 없는 프로젝트는 건너뛰고 집계에 표시한다

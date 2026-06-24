---
name: handbook-update
description: git diff 기반으로 stale 섹션을 판단하여 writable=true handbook 파일(README.md, ARCHITECTURE.md 등)을 섹션 단위로 갱신한다. --all로 전 프로젝트 순회, --now로 게이트 우회 즉시 갱신·신규 생성, --force로 전 섹션 재작성, --commit으로 갱신 후 자동 커밋을 지원한다.
argument-hint: [--project <key>] [--all] [--now [이름]] [--force] [--fix-only] [--add-only] [--trim] [--prune] [--sync] [--dry-run] [--file <path>] [--commit]
allowed-tools: Agent, Bash, Read, Write, Edit, Glob, Grep
---

## 역할

오케스트레이터: 인자를 파싱하고 `handbook-update-core` 에이전트를 호출한다.

## 프로젝트 해석

### 단일 프로젝트 모드 (기본, `--all` 없음)

1. `--project <key>` 인자가 있으면 그 프로젝트 사용
2. 없으면 `loregist project current` (cwd 기준 자동 추론)
3. 추론 실패 시 사용자에게 프로젝트 키 질문

`docs_root`: 추론된 프로젝트의 docs_root 값 (`loregist project list`로 확인)

→ loregist/CLAUDE.md "스킬 공통 — 프로젝트 추론 규칙" 적용

### 전 프로젝트 모드 (`--all`)

`--all` 인자가 있으면 `loregist project list --json` 결과 배열에서 전체 프로젝트 목록과 각 `docs_root`를 추출한다.

## 인수 정의

| 인수 | 설명 |
|---|---|
| `--project <key>` | 대상 프로젝트 키 명시 (생략 시 자동 추론) |
| `--all` | 전 프로젝트 순회 (loregist project list --json 기반) |
| `--now [이름]` | 게이트(`update_when`) 무시하고 즉시 갱신. `[이름]` 지정 시 handbook 파일명 매칭 필터 적용. 누락 파일 신규 생성 활성화 |
| `--force` | `--now`를 함의. 게이트 무시 + LOCK 외 전 섹션 재작성(additive enrichment — 기존 정확한 내용 보존+누락 추가+표현 보강, 오류만 삭제 허용) |
| `--dry-run` | stale 섹션 목록만 출력, 파일 수정·`.last_handbook_update` 갱신 건너뜀 |
| `--file <path>` | 특정 handbook 파일만 대상으로 처리 (docs_root 기준 상대경로) |
| `--commit` | 갱신 반영 후 git commit 자동 실행 (`docs: handbook update` 메시지) |
| `--defer-embed` | embed 단계를 스킵하고 갱신 파일 목록을 `EMBED_FILES: path1 path2 …` 형식으로 출력. 상위 wiki-update 스킬이 수집용으로 사용한다. |
| `--fix-only` | 오류·불일치만 최소 수정. 추가·보강 없음. 정확한 내용은 그대로 유지한다. |
| `--add-only` | 기존 내용 수정·삭제 없이 누락 항목 탐지 후 지정 형식으로 append만 수행. |
| `--trim` | 장황한 섹션을 탐지해 중복 설명·자명한 내용·과도한 예시를 제거하고 핵심만 남겨 압축. |
| `--prune` | 코드베이스에서 사라진 항목(모듈명·명령어·설정 키·경로 등)을 문서에서 제거. 추가·보강 없음. |
| `--sync` | enrichment + prune 양방향 동기화. additive enrichment와 dead content 제거를 동시 적용. |
| `--audit` | 수정 없이 문서 전체를 전수 진단. 오류·불일치·의미론적 문제를 LOCK 블록 내부 포함하여 출력한다. `--dry-run`(수정 예고)과 달리 "현재 문서에 무엇이 잘못됐는가"를 목적으로 한다. |
| `--suggest` | 수정 없이 개선 가능한 사항(표현·구조·의미론적 정확성)을 제안 출력. `--audit`(오류 진단)과 상호 보완: audit → 오류 목록, suggest → 개선 제안. |

## 플래그 조합 규칙

| 플래그 | stale 판정 | 재작성 방식 | 추가 | 삭제 | 압축 |
|---|---|---|---|---|---|
| (기본/`--now`) | diff 불일치 + 내용 현저 부족 | additive enrichment | O | 오류만 | X |
| `--force` | 전 섹션 무조건 | additive enrichment | O | 오류만 | X |
| `--fix-only` | 오류·불일치만 | 최소 수정 | X | 오류만 | X |
| `--add-only` | 누락 항목만 | append 전용 | O | X | X |
| `--trim` | 생략(장황도 탐지) | 압축 | X | 중복·자명 | O |
| `--prune` | 사라진 항목만 | 제거 전용 | X | dead content | X |
| `--sync` | prune+enrichment 통합 | additive enrichment + 제거 | O | dead content | X |
| `--audit` | 전수 진단(LOCK 포함) | 없음 | X | X | X |
| `--suggest` | 없음 | 없음 | X | X | X |

> `--trim`과 `--add-only`는 방향이 반대(압축 vs 추가)이므로 동시 사용 불가 (제약 조건 참조).

## 처리 흐름

### 1단계: 인자 파싱 + 프로젝트 추론

수신된 인자를 파싱하고 위 프로젝트 해석 규칙에 따라 `docs_root`와 프로젝트 key를 추론한다.

### 2단계: Agent 도구로 `handbook-update-core` 호출

Agent 도구를 사용해 `handbook-update-core` 에이전트를 호출한다. 호출 프롬프트에는 다음을 포함한다:

- 추론된 `docs_root` 경로
- 추론된 프로젝트 key
- 전달된 인자 전체: `--project`, `--all`, `--now [이름]`, `--force`, `--fix-only`, `--add-only`, `--trim`, `--prune`, `--sync`, `--dry-run`, `--file <path>`, `--commit`, `--defer-embed`
- `--all` 인자가 있으면 전체 프로젝트 목록과 각 `docs_root`도 함께 전달

### 3단계: 에이전트 완료 후 처리

에이전트 출력에서 다음을 파싱한다:

1. **`EDITED_FILES:` 줄 파싱** — 변경된 파일 목록 확인
2. **`git diff --stat` 출력** — dirty 상태 확인 (변경 사항 요약 표시)
3. **커밋 처리** — 우선순위 순으로 판단한다:

   a. **`--commit` 플래그 있음** (최우선) → 아래 커밋 명령을 즉시 실행한다:
      ```bash
      git add {변경된_파일_목록} {docs_root}/_wiki/.last_handbook_update
      git commit -m "docs: handbook update [$(date +%Y-%m-%d)]"
      ```
      `--all` 다중 repo 시에는 `references/output.md`의 repo 그룹핑 커밋 절차를 따른다.

   b. **`COMMIT_REQUESTED` 신호 있음** (두 번째 우선순위) → 위 a와 동일한 커밋 명령을 실행한다.

   c. **`--commit` 없고 `COMMIT_REQUESTED` 없음** → `auto_commit` 값으로 판단:
      - `loregist project list --json`에서 현재 프로젝트의 `auto_commit` 값을 읽는다.
      - `auto_commit: true` → 위 a와 동일한 커밋 명령을 자동 실행한다.
      - `auto_commit: false` (또는 미설정, 기본값 false) + `EDITED_FILES` 1건 이상:
        다음 제안 문구를 출력하고 사용자 승인을 기다린다:
        > 변경된 파일이 {N}개 있습니다. 커밋할까요? (projects.toml auto_commit: true 로 자동화 가능)
        - 승인 시 위 a와 동일한 커밋 명령을 실행한다.
        - 거절 시 커밋 없이 종료한다.
      - `EDITED_FILES` 0건 → 커밋/제안 없이 종료한다.

4. **embed 처리**:
   - `--defer-embed` 없고 `EDITED_FILES`에 파일이 있으면:
     ```bash
     LOREGIST_AUTO_GUARD=1 loregist embed --file <경로1> --file <경로2> …
     ```
   - `--defer-embed` 있으면 에이전트가 출력한 `EMBED_FILES:` 줄을 그대로 출력한다.

## 제약 조건

1. **기존 정확한 내용 삭제 금지**: 갱신 시 기존 내용 중 정확한 내용은 삭제하지 않는다. 삭제가 허용되는 경우는 다음 두 가지뿐이다:
   - 코드베이스와 명백히 불일치하는 오류인 경우
   - `--prune` 또는 `--sync` 플래그 사용 시 코드베이스에서 사라진 dead content인 경우
2. **`--add-only` 수정·삭제 금지**: `--add-only` 플래그 사용 시 기존 내용을 수정하거나 삭제하지 않는다. append만 허용한다. 오류가 있더라도 이 모드에서는 수정하지 않는다.
3. **`--trim`과 `--add-only` 상호 배타**: `--trim`(장황 섹션 압축)과 `--add-only`(누락 항목 추가)는 방향이 반대이므로 동시 사용 불가. 함께 지정된 경우 오류를 출력하고 종료한다.

# 트리거 키워드

- `handbook-update`, `handbook 갱신`, `handbook update`
- `README 갱신`, `ARCHITECTURE 갱신`, `문서 최신화`
- `handbook 업데이트`, `handbook 문서 갱신`

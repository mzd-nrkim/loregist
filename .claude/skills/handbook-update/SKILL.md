---
name: handbook-update
description: git diff 기반으로 stale 섹션을 판단하여 writable=true handbook 파일(README.md, ARCHITECTURE.md 등)을 섹션 단위로 갱신한다. --all로 전 프로젝트 순회, --now로 게이트 우회 즉시 갱신·신규 생성, --force로 전 섹션 재작성, --commit으로 갱신 후 자동 커밋을 지원한다.
argument-hint: [--project <key>] [--all] [--now [이름]] [--force] [--dry-run] [--file <path>] [--commit]
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
| `--force` | `--now`를 함의. 게이트 무시 + LOCK 외 전 섹션 재작성(기존 내용과 코드베이스 대조 후 전면 갱신) |
| `--dry-run` | stale 섹션 목록만 출력, 파일 수정·`.last_handbook_update` 갱신 건너뜀 |
| `--file <path>` | 특정 handbook 파일만 대상으로 처리 (docs_root 기준 상대경로) |
| `--commit` | 갱신 반영 후 git commit 자동 실행 (`docs: handbook update` 메시지) |
| `--defer-embed` | embed 단계를 스킵하고 갱신 파일 목록을 `EMBED_FILES: path1 path2 …` 형식으로 출력. 상위 wiki-update 스킬이 수집용으로 사용한다. |

## 처리 흐름

### 1단계: 인자 파싱 + 프로젝트 추론

수신된 인자를 파싱하고 위 프로젝트 해석 규칙에 따라 `docs_root`와 프로젝트 key를 추론한다.

### 2단계: Agent 도구로 `handbook-update-core` 호출

Agent 도구를 사용해 `handbook-update-core` 에이전트를 호출한다. 호출 프롬프트에는 다음을 포함한다:

- 추론된 `docs_root` 경로
- 추론된 프로젝트 key
- 전달된 인자 전체: `--project`, `--all`, `--now [이름]`, `--force`, `--dry-run`, `--file <path>`, `--commit`, `--defer-embed`
- `--all` 인자가 있으면 전체 프로젝트 목록과 각 `docs_root`도 함께 전달

### 3단계: 에이전트 완료 후 처리

에이전트 출력에서 다음을 파싱한다:

1. **`EDITED_FILES:` 줄 파싱** — 변경된 파일 목록 확인
2. **`git diff --stat` 출력** — dirty 상태 확인 (변경 사항 요약 표시)
3. **`COMMIT_REQUESTED` 신호 처리** — 신호가 있으면 다음 커밋 명령을 실행한다:

   ```bash
   git add {변경된_파일_목록} {docs_root}/_wiki/.last_handbook_update
   git commit -m "docs: handbook update [$(date +%Y-%m-%d)]"
   ```

   `--all` 다중 repo 시에는 `references/output.md`의 repo 그룹핑 커밋 절차를 따른다.

4. **embed 처리**:
   - `--defer-embed` 없고 `EDITED_FILES`에 파일이 있으면:
     ```bash
     LOREGIST_AUTO_GUARD=1 loregist embed --file <경로1> --file <경로2> …
     ```
   - `--defer-embed` 있으면 에이전트가 출력한 `EMBED_FILES:` 줄을 그대로 출력한다.

# 트리거 키워드

- `handbook-update`, `handbook 갱신`, `handbook update`
- `README 갱신`, `ARCHITECTURE 갱신`, `문서 최신화`
- `handbook 업데이트`, `handbook 문서 갱신`

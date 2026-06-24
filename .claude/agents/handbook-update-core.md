---
name: handbook-update-core
description: handbook-update 스킬의 실행 코어. W-1~W-9 단계를 수행하며 writable=true handbook 파일의 stale 섹션을 편집한다. 에이전트 모드에서는 사용자 승인 없이 직접 Edit하고 dirty 상태로 반환한다.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

## 프로젝트 해석

### 단일 프로젝트 모드 (기본, `--all` 없음)

1. `--project <key>` 인자가 있으면 그 프로젝트 사용
2. 없으면 `loregist project current` (cwd 기준 자동 추론)
3. 추론 실패 시 호출자에게 프로젝트 키를 명시하도록 오류 반환

`docs_root`: 추론된 프로젝트의 docs_root 값 (`loregist project list`로 확인)

→ loregist/CLAUDE.md "스킬 공통 — 프로젝트 추론 규칙" 적용

이 스킬의 모든 상대 경로는 `{docs_root}/` 기준이다.

### 전 프로젝트 모드 (`--all`)

`--all` 인자가 있으면 단일 프로젝트 추론을 건너뛰고 전체 프로젝트를 순회한다.

```bash
loregist project list --json
```

결과 JSON 배열에서 각 프로젝트 항목을 순서대로 처리한다. 각 프로젝트별로:

1. 해당 프로젝트의 `docs_root`와 `handbook`을 읽어 `writable: true` 항목을 산정한다.
2. W-1 ~ W-8 단계를 **프로젝트별로 독립 실행**한다 (각 프로젝트의 `.last_handbook_update`를 각자 읽고 기록).
3. 이종 repo(git 루트가 다른 프로젝트)가 혼재해도 각 프로젝트별로 독립 처리하며, 말미에 전체 집계를 출력한다.

`--project <key>`와 `--all`이 동시에 지정된 경우 `--all`이 우선하며 전체 프로젝트를 순회한다.

# 역할

git diff를 분석하여 writable=true로 지정된 handbook 파일의 stale 섹션을 판단하고, 섹션 단위 Edit을 직접 반영한다. **handbook 파일을 *쓰는* 모든 규칙은 이 에이전트에 단일 귀속**된다.

# 인수 정의

## 인수 목록

| 인수 | 설명 |
|---|---|
| `--project <key>` | 대상 프로젝트 키 명시 (생략 시 자동 추론) |
| `--all` | 전 프로젝트 순회 (loregist project list --json 기반) |
| `--now [이름]` | 게이트(`update_when`) 무시하고 즉시 갱신. `[이름]` 지정 시 handbook 파일명 매칭 필터 적용. 누락 파일 신규 생성 활성화 |
| `--force` | `--now`를 함의. 게이트 무시 + LOCK 외 전 섹션 재작성(기존 내용과 코드베이스 대조 후 전면 갱신) |
| `--dry-run` | stale 섹션 목록만 출력, 파일 수정·`.last_handbook_update` 갱신 건너뜀 |
| `--file <path>` | 특정 handbook 파일만 대상으로 처리 (docs_root 기준 상대경로) |
| `--commit` | 갱신 반영 후 git commit 자동 실행 (`docs: handbook update` 메시지) — 에이전트는 편집 완료 후 `COMMIT_REQUESTED` 신호를 출력하고, 실제 커밋은 호출자(래퍼)가 수행 |
| `--defer-embed` | embed 단계를 스킵하고 갱신 파일 목록을 `EMBED_FILES: path1 path2 …` 형식으로 출력. 상위 wiki-update 스킬이 수집용으로 사용한다. |

> 인수 3축 의미·함의 규칙·대표 조합 매트릭스·`--now <이름>` 필터 동작·`--file`과 `--now` 병존 규칙(D1) 세부는 `../skills/handbook-update/references/cli.md` 참조 — 인수 해석이 모호하거나 조합 동작을 확인할 때 읽는다.

---

# 실행 흐름 (W-1 ~ W-9)

아래는 각 단계의 한 줄 요약이다. 판정 세부·분기 규칙 전체는 `../skills/handbook-update/references/gates.md` 참조 — 각 단계 진입 시 해당 섹션을 읽는다.

## W-1. base 결정

`.last_handbook_update`에서 커밋 SHA를 읽어 diff base를 결정한다. 파일 없음·빈 파일·무효 SHA이면 전체 평가 모드로 폴백한다. `--now`/`--force` 시 이 단계를 건너뛴다.

## W-2. git diff 기반 변경 파악

`git log <base>..HEAD`로 커밋을 확인하고, 커밋 0건이면 전체 평가 모드로 자동 폴백한다. `--now`/`--force` 시 건너뛴다.

## W-3. writable=true 파일 목록 추출

`loregist project list --json`으로 `handbook`에서 `writable: true` 항목만 추출한다. `--file` 지정 시 해당 파일의 writable 여부를 확인한다.

## W-4. update_when 갱신 판단 게이트

각 파일의 `update_when` 조건을 diff 맥락과 대조하여 갱신 포함·제외를 결정한다. `--now`/`--force`·전체 평가 모드에서는 전부 통과 처리한다.

## W-5. stale 섹션 판단

`##` 기준 섹션 분할 후 stale/최신/무관을 판정한다. `--force` 시 LOCK 외 전 섹션을 재작성 대상으로 간주한다. 판정 결과 목록을 출력한다.

## W-6. LOCK 마커 보호 영역 규칙

`<!-- LOCK:START -->` ~ `<!-- LOCK:END -->` 내부는 어떤 경우에도 수정·삭제 금지다.

## W-6b. 신규 파일 생성 흐름 (`--now`/`--force` 활성 시)

`writable: true`로 선언됐지만 디스크에 없는 파일을 코드베이스 분석으로 초안 작성 후 직접 Write한다. 기본 증분 모드에서는 이 단계를 건너뛴다.

## W-7. 섹션 단위 직접 Edit 흐름

에이전트 모드에서는 사용자 승인 없이 stale 섹션을 직접 Edit한다. 다음 규칙을 따른다:

### `--dry-run` 모드

`--dry-run` 인자가 있으면 섹션 목록만 출력하고 종료한다. 파일 수정 및 `.last_handbook_update` 갱신을 일절 수행하지 않는다.

```
[dry-run] stale 섹션 목록:
  README.md §배포 파이프라인 — 새 서비스 추가로 갱신 필요
  ARCHITECTURE.md §시스템 구성도 — 모듈 구조 변경으로 갱신 필요

파일 수정 및 .last_handbook_update 갱신을 건너뛰었습니다.
```

### `auto_handbook_update=true` 프로젝트

`auto_handbook_update` 플래그가 켜진 프로젝트는 기존과 동일하게 자동 진행한다 (에이전트 모드에서는 이미 해당 조건이 충족된 상태로 간주).

### 직접 Edit 절차

stale 섹션 각각에 대해 다음을 수행한다:

1. 해당 섹션의 현재 내용을 읽는다.
2. 코드베이스 현 상태와 대조하여 갱신 내용을 생성한다.
3. LOCK 마커 보호 영역을 피해 해당 섹션만 Edit 툴로 즉시 수정한다.
4. 파일이 dirty 상태로 남는다 — 커밋은 에이전트가 수행하지 않는다.

**LOCK 보호 영역(W-6)과 `update_when` 게이트(W-4)는 에이전트 모드에서도 그대로 적용된다.**

### 신규 파일 생성 (W-6b 연계)

`--now`/`--force` 활성 시, 디스크에 없는 `writable: true` 파일은 코드베이스 분석으로 초안 작성 후 Write 툴로 즉시 생성한다 (사용자 확인 없음).

## W-8. `.last_handbook_update` 갱신

Edit/Write 반영이 1건 이상인 경우에만 `_wiki/.last_handbook_update`에 HEAD SHA(git repo) 또는 ISO 8601 타임스탬프(비git)를 기록한다.

> W-1 ~ W-8 판정 세부 전체는 `../skills/handbook-update/references/gates.md` 참조.

## W-9. embed 단계 및 완료 신호 출력

`--defer-embed` 없으면 반영된 파일을 `LOREGIST_AUTO_GUARD=1 loregist embed --file …`로 직접 embed한다. `--defer-embed` 있으면 `EMBED_FILES: path1 path2 …` 한 줄을 출력하고 호출자에 위임한다. 갱신 0건·`--dry-run` 시 건너뛴다.

### 완료 출력 형식

실행 완료 후 반드시 다음 신호를 출력한다:

**갱신 파일이 있을 때 (--defer-embed 없음):**
```
EDITED_FILES: path1 path2 ...
```

**갱신 파일이 있을 때 (--defer-embed 있음):**
```
EDITED_FILES: path1 path2 ...
EMBED_FILES: path1 path2 ...
```

**--commit 지정 시 (EDITED_FILES 출력 다음에 추가):**
```
COMMIT_REQUESTED
```

**갱신 0건 또는 --dry-run 시:**
```
EDITED_FILES:
```
(빈 목록 — 호출자가 파싱 가능)

> W-9 세부(재귀 차단·`--all` 합산 규칙)는 `../skills/handbook-update/references/gates.md` 참조.

> 출력 형식(단일/`--all`/`--commit`) 및 연계 흐름은 `../skills/handbook-update/references/output.md` 참조 — 완료 출력 작성 시 읽는다.

---

# 제약 조건

1. **writable=false이거나 문자열 형식인 handbook 항목은 읽기 전용 — 수정 절대 금지** (심층 방어 2차 — 프롬프트 규칙)

   - `handbook` 항목이 문자열 형식(예: `"README.md"`)이거나, 객체 형식이더라도 `writable: false`(또는 `writable` 키 미존재)인 경우, 해당 파일은 **스캔(읽기)만 허용**하며 Write·Edit 등 쓰기 도구 사용이 금지된다.
   - 반대로 **`writable: true`로 명시된 항목만이 쓰기(Edit/Write) 대상**이다. W-3에서 추출한 `writable=true` 목록에 없는 파일은 설령 존재하더라도 수정하지 않는다.
   - **신규 파일 Write도 `writable: true` 경로 한정**: W-6b의 신규 생성 흐름에서 Write 툴로 파일을 생성하는 경우도, `handbook`에 `writable: true`로 선언된 경로에만 허용된다. `writable: true`로 선언되지 않은 경로에 새 파일을 생성하지 않는다. 이 규칙은 1차 hook 방어(PreToolUse)와 정합된다.
   - **1차 방어(코드/하네스 레벨)**: PreToolUse hook(`settings.json`)이 Edit/Write/NotebookEdit 호출을 인터셉트하여, `file_path`가 현재 프로젝트의 `writable=false`(및 문자열 형식) handbook 경로 집합에 포함되면 **하네스 수준에서 자동 차단**한다. LLM의 규칙 준수 의지와 무관하게 결정적(deterministic)으로 동작한다.
   - **2차 방어(프롬프트 규칙 — 본 항목)**: 1차 hook이 미작동하거나 스코프 밖인 상황에서도 이 프롬프트 규칙이 추가 방어선으로 작동한다. "코드 1차 + 프롬프트 2차"의 심층 방어(defense in depth).

2. **LOCK 마커 보호 영역 수정 금지** — `<!-- LOCK:START -->` ~ `<!-- LOCK:END -->` 내부는 일절 수정·삭제 불가 (W-6 참조). `--force` 재작성 시에도 동일하게 적용된다.
3. `--dry-run` 시 파일 Write·Edit 금지 — 출력만 (`--now`/`--force`와 함께 지정해도 동일)
4. `--dry-run` 시 `.last_handbook_update` 갱신 금지
5. 반영이 1건 이상 있을 때만 `.last_handbook_update` 갱신 (변경없음·dry-run 시 건너뜀)
6. `update_when` 조건 불부합 시 해당 파일 갱신 제외 — 단, 스캔(읽기)은 수행 가능. `--now`/`--force` 시 이 규칙이 무효화된다.
7. `_wiki/*.md` 파일(T-xxx, D-xxx)은 이 에이전트의 갱신 대상이 아님 — catalog-update-core 에이전트 사용
8. **신규 생성은 `--now` 또는 `--force` 시에만**: 기본 증분 모드에서는 `writable: true` 파일이 디스크에 없어도 신규 생성하지 않는다.
9. **스탬프 부재·빈 파일·무효 SHA는 모두 전체 평가 폴백**: `.last_handbook_update` 파일이 없거나 내용이 비어 있거나, 기록된 SHA가 git 히스토리에 존재하지 않는 경우(강제 rebase·reset 후 등), `main` 브랜치 fallback 없이 **첫 실행과 동일한 전체 평가 모드로 폴백**한다. `update_when` 게이트는 통과 처리.
10. **빈-diff 폴백은 스탬프 갱신 조건과 무관**: W-2 빈-diff 가드로 전체 평가 모드에 진입한 경우라도, 갱신 0건이면 스탬프를 기록하지 않는다(다음 실행도 전체 평가 재진입 — 의도된 동작).
11. **git commit/push 금지**: 에이전트는 파일 편집만 수행한다. 커밋은 `COMMIT_REQUESTED` 신호를 출력하고, 실제 실행은 호출자(래퍼 SKILL.md)가 담당한다.

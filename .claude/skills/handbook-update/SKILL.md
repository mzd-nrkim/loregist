---
name: handbook-update
description: git diff 기반으로 stale 섹션을 판단하여 writable=true handbook 파일(README.md, ARCHITECTURE.md 등)을 섹션 단위로 갱신한다. --all로 전 프로젝트 순회, --now로 게이트 우회 즉시 갱신·신규 생성, --force로 전 섹션 재작성, --commit으로 갱신 후 자동 커밋을 지원한다.
argument-hint: [--project <key>] [--all] [--now [이름]] [--force] [--dry-run] [--file <path>] [--commit]
allowed-tools: Agent, Bash, Read, Write, Edit, Glob, Grep
---

## 프로젝트 해석

### 단일 프로젝트 모드 (기본, `--all` 없음)

1. `--project <key>` 인자가 있으면 그 프로젝트 사용
2. 없으면 `loregist project current` (cwd 기준 자동 추론)
3. 추론 실패 시 사용자에게 프로젝트 키 질문

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

git diff를 분석하여 writable=true로 지정된 handbook 파일의 stale 섹션을 판단하고, 섹션 단위 Edit을 사용자 승인 후 반영한다. **handbook 파일을 *쓰는* 모든 규칙은 이 스킬에 단일 귀속**된다.

# 트리거 키워드

- `handbook-update`, `handbook 갱신`, `handbook update`
- `README 갱신`, `ARCHITECTURE 갱신`, `문서 최신화`
- `handbook 업데이트`, `handbook 문서 갱신`

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
| `--commit` | 갱신 반영 후 git commit 자동 실행 (`docs: handbook update` 메시지) |
| `--defer-embed` | embed 단계를 스킵하고 갱신 파일 목록을 `EMBED_FILES: path1 path2 …` 형식으로 출력. 상위 wiki-update 스킬이 수집용으로 사용한다. |

## 3축 의미

이 스킬의 인수는 세 독립 축으로 구성된다:

| 축 | 인수 | 의미 |
|---|---|---|
| **범위** | `--all` | 단일 프로젝트(기본) vs 전 프로젝트 순회 |
| **게이트** | `--now [이름]` | `update_when` 게이트 적용(기본) vs 게이트 무시 즉시 갱신 |
| **깊이** | `--force` | 증분 섹션 갱신(기본) vs LOCK 외 전 섹션 재작성 |

## 함의 규칙

- **`--force` ⇒ `--now`**: `--force` 지정 시 `--now`를 명시하지 않아도 게이트가 자동으로 꺼진다.
- **누락 생성 ⊂ `--now`**: `writable=true`로 선언됐지만 디스크에 존재하지 않는 파일의 신규 생성은 `--now`(또는 `--force`) 시에만 활성화된다. 기본 증분 모드에서는 기존 파일 갱신만 수행한다.

## 대표 조합 매트릭스

| 조합 | 게이트(`update_when`) | 깊이 | 신규 생성 | 비고 |
|---|---|---|---|---|
| (무인자) — 첫 실행 또는 빈-diff 폴백 | 무시(전체 평가) | 증분 | 비활성 | 스탬프 부재·무효 SHA·0커밋 시 자동 진입. **승인 유지** (게이트만 우회 — `--now`와 동일, 단 게이트는 사용자 승인 단계와 무관) |
| (무인자) — 정상 증분 | 적용 | 증분 | 비활성 | 회귀 없음 — 스탬프 SHA 유효 + 커밋 有 |
| `--now` | 무시 | 증분 | 활성 | 즉시 갱신, 파일명 필터 없음. **W-1·W-2 건너뜀** |
| `--now 이름` | 무시 | 증분 | 활성 | 파일명 매칭된 파일만 대상 |
| `--force` | 무시(함의) | 전 섹션 재작성 | 활성 | 전면 갱신 |
| `--all` | 적용(증분) / 전체 평가(첫 실행) | 증분 | 비활성 | 전 프로젝트 — 프로젝트별 스탬프 상태에 따라 모드 결정 |
| `--all --now` | 무시 | 증분 | 활성 | 전 프로젝트 즉시 갱신 |
| `--all --force` | 무시(함의) | 전 섹션 재작성 | 활성 | 전 프로젝트 전면 갱신 |
| `--dry-run` | 적용 | 증분 | 비활성 | 출력 전용 |
| `--commit` | 적용 | 증분 | 비활성 | 갱신 후 자동 커밋 |

> **첫 실행/빈-diff 폴백 vs `--now` 차이**: 둘 다 `update_when` 게이트를 통과 처리하고 코드베이스 현 상태 기준으로 stale 판단한다. 단, `--now`는 W-1·W-2 자체를 건너뛰는 "명시적 게이트 우회"이고, 첫 실행/빈-diff 폴백은 증분 모드 진입 시 조건에 따라 **자동으로** 전체 평가로 전환된다. 사용자 승인(W-7) 단계는 두 경우 모두 동일하게 유지된다. 신규 파일 생성은 `--now`/`--force` 명시 시에만 활성화되며 첫 실행/빈-diff 폴백은 해당 없다.

## `--now <이름>` 필터 동작

`--now` 뒤에 이름을 지정하면 handbook 파일명(확장자 포함 또는 제외)을 매칭하는 필터로 동작한다.

- 매칭 대상: `handbook`에서 `writable: true`인 항목의 파일명 부분 (`README.md`, `ARCHITECTURE.md` 등)
- 매칭 규칙: 지정한 이름이 파일명(확장자 포함/제외 모두)에 포함되면 매칭. 대소문자 무시.
  - 예: `--now README` → `README.md`, `README` 모두 매칭
  - 예: `--now arch` → `ARCHITECTURE.md` 매칭
- 매칭된 파일만 W-4 이후 대상으로 삼는다. 매칭 결과가 없으면 사용자에게 알리고 종료한다.

## `--file`과 `--now <이름>` 병존 규칙 (D1)

`--file <path>`와 `--now <이름>`을 동시에 지정하면 **`--file`이 우선**한다.

- `--file`은 경로 기반 단일 파일 정밀 지정이며, `--now <이름>` 파일명 필터보다 구체적이다.
- 이 경우 `--now <이름>`의 파일명 필터는 무시되고, `--file`로 지정한 단일 파일만 처리한다.
- `--now`의 게이트 무시 효과는 `--file`과 병존할 때도 그대로 적용된다.

---

# W-1. base 결정

## `--now` / `--force` 시 생략 경로

`--now` 또는 `--force` 인자가 있으면 git diff base 결정 단계(W-1)와 diff 분석 단계(W-2)를 **건너뛴다**.

- W-4(update_when 게이트)도 함께 통과(후술)하므로 W-3 → W-4(통과) → W-5 이후로 직행한다.
- `--now`/`--force` 시 W-5 stale 판단은 git diff 내용 대신 **코드베이스 현 상태**를 기준으로 각 섹션을 평가한다.

## 1단계: `.last_handbook_update` 읽기 (기본 증분 모드에서만)

```bash
cat {docs_root}/_wiki/.last_handbook_update 2>/dev/null
```

- 파일이 존재하고 내용이 있으면: 해당 **커밋 SHA** 1줄을 base로 사용
- **파일이 없거나 비어 있으면: 첫 실행으로 간주하여 "전체 평가 모드"로 전환한다** — W-3 → W-4(전체 평가 규칙 적용) → W-5(코드베이스 현 상태 기준 평가)로 직행한다. `--now`와 평가 기준은 동일하되, **사용자 승인(W-7) 단계는 유지**한다(게이트 우회와 구분되는 핵심).

## 2단계: base 확인 (기본 증분 모드에서만, 스탬프 SHA가 존재하는 경우)

```bash
# base가 SHA인 경우
git log --oneline -1 <sha>
```

SHA가 유효하지 않으면(git 히스토리에 존재하지 않는 경우 — 강제 rebase·reset 후 등) **첫 실행과 동일하게 전체 평가 모드로 폴백**하고 사용자에게 한 줄로 알린다.

> 이로써 `.last_handbook_update` 부재, 내용 빈 파일, 무효 SHA 세 케이스 모두 전체 평가 폴백으로 처리된다.

---

# W-2. git diff 기반 변경 파악

> `--now` 또는 `--force` 인자가 있으면 이 단계 전체를 건너뛴다 (W-1 참조).

## 커밋 로그 확인

```bash
git log <base>..HEAD --oneline
```

## 빈-diff 가드

스탬프가 존재하고 유효한 SHA가 base로 결정된 경우라도, 아래를 실행하여 커밋 수를 확인한다.

```bash
git rev-list --count <base>..HEAD
```

결과가 `0`이면(브랜치 끝이 base와 동일 — main 브랜치 자기상쇄 등) "변경 없음 종료" 대신 **전체 평가 모드로 자동 폴백**한다. 사용자에게 다음과 같이 한 줄로 알린다:

```
[handbook-update] base..HEAD 커밋이 없어 전체 평가 모드로 폴백합니다. (base: <sha>)
```

전체 평가 폴백 후에는 W-3 → W-4(전체 평가 규칙 적용) → W-5(코드베이스 현 상태 기준)로 직행한다.

## 변경 내용 분석

커밋이 1개 이상인 경우에만 아래를 실행한다:

```bash
git diff <base> HEAD
```

- 변경된 파일 목록과 각 파일의 diff를 파싱한다.
- `--file <path>` 인자가 있으면 해당 파일과 관련된 diff에 집중한다.
- **유효 SHA + base..HEAD 커밋이 1개 이상이나 handbook 관련 diff가 없으면** "변경 사항 없음"을 출력하고 종료한다. (0커밋 케이스는 위 빈-diff 가드에서 이미 처리됨)

---

# W-3. writable=true 파일 목록 추출

```bash
loregist project list --json
```

결과에서 현재 프로젝트의 `handbook` 배열을 읽어 `writable: true`인 항목만 추출한다.

```
# writable=true 항목 예시
{path: "README.md", writable: true}
{path: "ARCHITECTURE.md", writable: true, update_when: "새 서비스가 추가될 때"}
```

- `--file <path>` 인자가 있으면 해당 파일이 writable=true인지 확인하고, 아니면 오류를 출력하고 종료한다.
- writable=true 파일이 하나도 없으면 사용자에게 알리고 종료한다.

---

# W-4. update_when 갱신 판단 게이트

**handbook 파일을 쓰는 모든 규칙은 이 스킬에 귀속된다.** `update_when` 조건 판정도 이 스킬에서 수행한다.

## `--now` / `--force` 시 게이트 통과

`--now` 또는 `--force` 인자가 있으면 `update_when` 조건 판정을 **건너뛰고 모든 writable=true 파일을 게이트 통과로 간주**한다.

- 게이트 통과 이유를 출력할 필요 없음 — W-5 이후로 바로 진행한다.
- `--now <이름>` 필터가 함께 지정된 경우 게이트 통과 후 파일명 매칭 필터를 적용한다.

## 전체 평가 모드(첫 실행 / 빈-diff 폴백) 시 게이트 취급

**전체 평가 모드**(W-1에서 스탬프 부재·내용 빈 파일·무효 SHA로 진입하거나, W-2 빈-diff 가드로 폴백된 경우)에서는 `--now`와 동일하게 `update_when` 게이트를 **통과 처리**하고 모든 writable=true 파일을 갱신 대상으로 간주한다(안 1 확정 — 첫 실행은 전수 점검이 의미상 자연스럽고, 변경 맥락이 없는 상태에서 `update_when` 조건을 판정하면 맥락 빈약으로 판정이 모호해짐). 단 **사용자 승인(W-7)은 유지**한다.

## 기본 증분 모드 판정 흐름

항목에 `update_when` 값이 존재하면, W-2에서 파악한 변경 맥락(git diff 내용)이 그 조건에 부합하는지 LLM이 먼저 판정한다.

| 조건 | 처리 |
|---|---|
| `update_when` 없음 | 일반 staleness 판단으로 진행 (하위호환) |
| `update_when` 있음 + 현재 변경 맥락이 조건에 **부합** | 해당 파일 갱신 대상 포함. 근거 문구 출력: `이 파일은 '{update_when}' 조건에 해당해 갱신을 제안합니다.` |
| `update_when` 있음 + 현재 변경 맥락이 조건에 **불부합** | 해당 파일은 갱신 제외(스캔만). 이유를 한 줄로 출력 |

게이트 통과 후에도 W-5(stale 판단)·W-6(LOCK 보호)·W-7(승인 흐름)이 그대로 적용된다.

---

# W-5. stale 섹션 판단

갱신 대상으로 포함된 writable=true 파일 각각을 읽고 `##` 기준으로 섹션 단위로 분할한다.

## `--force` 시: 전 섹션 재작성 분기

`--force` 인자가 있으면 staleness 판단을 건너뛰고 **LOCK 마커 보호 영역을 제외한 모든 섹션을 갱신 대상**으로 간주한다.

- 각 섹션을 코드베이스 현 상태와 대조하여 내용 전체를 새로 작성한다.
- LOCK 마커(`<!-- LOCK:START -->` ~ `<!-- LOCK:END -->`) 안쪽 내용은 재작성에서 제외한다 (W-6 동일 규칙 적용).
- "최신/무관" 판정 없이 전 섹션이 W-7 승인 흐름으로 진입한다.

## 기본 증분 모드 / `--now` 모드: staleness 판단 기준

- **기본 증분 모드**: W-2의 git diff 내용과 각 섹션을 매핑하여 판단
- **`--now` 모드 (diff 없음)**: 코드베이스 현 상태를 직접 읽어 섹션 내용과 비교

| 판정 | 기준 |
|---|---|
| **stale** | 변경(신규 모듈·API·구조 변경 등)이 해당 섹션과 불일치하거나 반영되지 않은 경우 |
| **최신** | 섹션 내용이 현재 코드베이스 상태와 일치하는 경우 |
| **무관** | diff/코드베이스 변경과 해당 섹션이 관련 없는 경우 |

## stale 판정 목록 출력

```
## handbook-update 분석 결과

base: <sha>  (정상 증분 모드)
  또는 base: 첫 실행(전체 평가)  (스탬프 부재·빈 파일·무효 SHA로 인한 전체 평가 모드)
  또는 base: 빈-diff 폴백(전체 평가)  (W-2 빈-diff 가드로 자동 폴백된 전체 평가 모드)
  또는 "--now 모드 — diff 생략" (--now/--force 시)
변경 커밋: {N}개  (정상 증분 모드에서만 — 전체 평가·--now/--force 시 생략)

### stale 섹션 목록
- README.md §배포 파이프라인 — 새 서비스 추가로 인해 갱신 필요
- ARCHITECTURE.md §시스템 구성도 — 모듈 구조 변경으로 인해 갱신 필요

### 최신/무관 섹션 (갱신 불필요)
- README.md §소개 — 변경 없음
```

---

# W-6. LOCK 마커 보호 영역 규칙

**writable=true 파일을 갱신할 때 아래 마커로 표시된 보호 영역을 반드시 준수한다.**

```
<!-- LOCK:START -->
(보호 영역 내부 — 수정·삭제 금지)
<!-- LOCK:END -->
```

- `<!-- LOCK:START -->` ~ `<!-- LOCK:END -->` 사이 내용은 **일절 수정·삭제 금지**
- 보호 영역 **외부**는 추가·수정·삭제 허용
- LOCK 마커가 없는 파일은 파일 전체가 수정 가능 영역으로 간주
- stale 판단 시 LOCK 영역 내부 내용은 stale 판정에서 제외한다

---

# W-6b. 신규 파일 생성 흐름 (`--now` / `--force` 활성 시)

`--now` 또는 `--force` 인자가 있을 때만 이 단계를 실행한다. 기본 증분 모드에서는 건너뛴다.

## 디스크 존재 여부 분기

W-3에서 추출한 `writable: true` 항목 중 **디스크에 파일이 존재하지 않는 항목**을 신규 생성 대상으로 선정한다.

```bash
# 각 writable=true 항목에 대해
ls {docs_root}/{path} 2>/dev/null || echo "MISSING"
```

파일이 존재하면 기존 갱신 흐름(W-5 → W-7)으로 처리한다. 파일이 없으면 아래 신규 생성 흐름을 따른다.

## 파일명 역할 규약 → 초안 생성

파일명으로 역할을 추론하여 코드베이스를 분석한 뒤 초안을 작성한다.

| 파일명 패턴 | 역할 추론 | 초안 기준 |
|---|---|---|
| `README` / `README.md` | 프로젝트 개요·시작 가이드 | 프로젝트 구조·설치·실행 방법 중심 |
| `ARCHITECTURE` / `ARCHITECTURE.md` | 시스템 구성·설계 | 모듈 구조·의존성·데이터 흐름 중심 |
| `USAGE` / `USAGE.md` | 사용 방법·예시 | CLI/API 사용법·예제 코드 중심 |
| 기타 파일명 | 파일명 + 코드베이스 분석으로 추론 | 파일명이 암시하는 주제를 코드베이스에서 탐색 |

초안은 코드베이스를 직접 읽어(Read/Glob/Grep) 실제 내용을 기반으로 작성한다. 추측으로 채우지 않는다.

## 승인 후 Write 절차

```
### {파일명} 신규 생성 제안

[초안 내용]
...

이 파일을 생성할까요? (예/아니요/모두 승인/모두 취소)
```

- 사용자가 승인하면 Write 툴로 `{docs_root}/{path}`에 파일을 생성한다.
- **LOCK 마커 없이 생성**한다 (신규 파일이므로 보호 영역 없음).
- 신규 생성도 `writable: true` 경로에 한정한다 (제약 조건 참조).
- `--dry-run` 모드에서는 신규 생성도 건너뛰고 목록만 출력한다.

---

# W-7. 섹션 단위 Edit 제안 + 사용자 승인 흐름

**사용자 승인 없이는 파일을 수정하지 않는다.** LLM은 변경 내용을 제안하고 사용자가 승인한 뒤에만 파일을 수정한다.

## 예외 (플래그=사전 승인)

대상 프로젝트에 `auto_handbook_update`가 켜져 있으면 그 플래그가 사용자 사전 승인을 대체한다 — 매 호출 승인 프롬프트를 생략하고 무인 갱신을 진행한다.

단 이는 승인 단계만 대체할 뿐, **LOCK 보호 영역(W-6)은 여전히 미수정**이고 **`update_when` 게이트(W-4)는 그대로 적용**된다(조건 불부합 파일은 무인이라도 미갱신). 플래그가 꺼져 있으면(기본) 종전대로 승인 전 미수정.

> **우선순위**: 이 예외는 `writable=false` 코드레벨 차단(P5) 및 `update_when` 게이트보다 하위다 — 그 두 게이트는 `auto_handbook_update` 플래그와 무관하게 항상 우선한다.

## --dry-run 모드

`--dry-run` 인자가 있으면 섹션 목록만 출력하고 종료한다. 파일 수정 및 `.last_handbook_update` 갱신을 일절 수행하지 않는다.

```
[dry-run] stale 섹션 목록:
  README.md §배포 파이프라인 — 새 서비스 추가로 갱신 필요
  ARCHITECTURE.md §시스템 구성도 — 모듈 구조 변경으로 갱신 필요

파일 수정 및 .last_handbook_update 갱신을 건너뛰었습니다.
```

## 승인 흐름

stale 섹션이 있으면, 각 섹션에 대해 다음 순서로 진행한다.

### 1단계: 갱신 내용 초안 제시

```
### README.md §배포 파이프라인 갱신 제안

이 파일은 '새 서비스가 추가될 때' 조건에 해당해 갱신을 제안합니다.  (update_when 있는 경우)

[현재 내용]
...

[제안 내용]
...

이 섹션을 갱신할까요? (예/아니요/모두 승인/프로젝트 모두 승인/모두 취소)
```

### 2단계: 사용자 응답 처리

| 응답 | 처리 |
|---|---|
| **예** | 해당 섹션만 Edit 툴로 반영 |
| **아니요** | 해당 섹션 건너뜀 |
| **모두 승인** | 남은 stale 섹션 **및 신규 생성 대상** 전체 반영 |
| **프로젝트 모두 승인** | 현재 프로젝트의 남은 섹션·신규 파일 전체를 승인 후 다음 프로젝트로 진행 (`--all` 모드에서만 유효; 단일 프로젝트 모드에서는 "모두 승인"과 동일) |
| **모두 취소** | 남은 섹션 전체 건너뜀 |

### 3단계: Edit 반영 (승인 시)

LOCK 마커 보호 영역을 피해 해당 섹션만 Edit 툴로 수정한다.

---

# W-8. `.last_handbook_update` 갱신

Edit/Write 반영(사용자 승인)이 **1건 이상 성공**한 뒤에만 `_wiki/.last_handbook_update`를 갱신한다.

## 전체 평가 모드에서의 상태 전이

**전체 평가 모드**(첫 실행 또는 빈-diff 폴백)에서 갱신이 **1건 이상** 반영되면, 기존 규칙과 동일하게 `_wiki/.last_handbook_update`에 `git rev-parse HEAD` 결과 SHA를 기록한다. 이 SHA가 다음 실행의 base가 되어 **정상 증분 모드로 자동 전환**된다.

전체 평가 모드에서 stale 섹션이 없거나 사용자가 모든 섹션을 거부하여 갱신이 **0건**이면 스탬프는 기록하지 않는다. 다음 실행도 다시 전체 평가 모드로 진입한다. 이는 악순환이 아니라 "변경 없으면 매번 현 상태 점검"이라는 **의도된 동작**이다 — 코드베이스가 handbook과 이미 정합된 상태이므로 스탬프를 찍을 필요가 없다.

## 프로젝트별 git repo 여부에 따른 조건부 스탬프 규칙

| 상황 | 스탬프 내용 |
|---|---|
| 프로젝트 `docs_root`가 git repo 안에 있음 | `git rev-parse HEAD` 결과 SHA 40자를 1줄로 기록 |
| 프로젝트 `docs_root`가 git repo 밖에 있음 (git 미사용) | ISO 8601 타임스탬프(`date -u +%Y-%m-%dT%H:%M:%SZ`)를 1줄로 기록 |

git repo 여부 확인:

```bash
git -C {docs_root} rev-parse --is-inside-work-tree 2>/dev/null && echo "git" || echo "no-git"
```

결과를 `{docs_root}/_wiki/.last_handbook_update`에 1줄로 기록한다.

**`--all` 모드**: 각 프로젝트별로 독립적으로 스탬프를 기록한다. 한 프로젝트의 갱신이 없어도 다른 프로젝트의 스탬프 기록에 영향을 주지 않는다.

**갱신 건너뜀 조건 (다음 중 하나라도 해당):**

- 변경 사항 없음 (W-2에서 diff 없음)
- stale 섹션 없음 (W-5에서 전부 최신/무관)
- 모든 섹션 거부됨 (W-7에서 전부 아니요/모두 취소)
- `--dry-run` 모드

---

# 출력 형식

## 단일 프로젝트 완료 출력

```
## handbook-update 완료

프로젝트: <key>
base: <sha>  (정상 증분) / 첫 실행(전체 평가) / 빈-diff 폴백(전체 평가) / "--now 모드" / "--force 모드"
대상 파일: {N}개 (writable=true)
stale 섹션: {N}개
신규 생성: {N}개  (--now/--force 시에만)
반영: {N}개 (승인) / {N}개 (거부) / {N}개 (dry-run 건너뜀)

### 반영 목록
- README.md §배포 파이프라인 — 갱신 완료
- ARCHITECTURE.md §시스템 구성도 — 갱신 완료

### 신규 생성 파일  (--now/--force 시에만)
- USAGE.md — 신규 생성 완료

### 건너뜀
- README.md §소개 — 사용자 거부

.last_handbook_update: <HEAD SHA 또는 타임스탬프>  (갱신된 경우)
또는
.last_handbook_update: 갱신 건너뜀 (변경없음/전부거부/dry-run)
```

## `--all` 모드: 프로젝트별 집계 + 전체 집계

각 프로젝트 처리 후 개별 요약을 출력하고, 전체 처리 완료 후 집계를 출력한다.

```
## handbook-update 전체 집계 (--all)

처리 프로젝트: {N}개
총 갱신 섹션: {N}개 (승인) / {N}개 (거부)
총 신규 생성: {N}개
총 건너뜀: {N}개 (변경없음·불부합·거부)

### 프로젝트별 요약
- project-a: 갱신 2건, 신규 1건
- project-b: 변경 없음 (건너뜀)
- project-c: 갱신 1건, 거부 1건
```

## `--commit` 모드 추가 출력

`--commit` 인자가 있고 반영이 1건 이상 성공한 경우, W-8 이후 자동으로 git commit을 실행한다.

### 단일 repo (단일 handbook 경로 또는 같은 git repo에 속한 복수 경로)

```bash
git add {변경된_파일_목록} .last_handbook_update
git commit -m "docs: handbook update [$(date +%Y-%m-%d)]"
```

```
커밋: <커밋 SHA> — "docs: handbook update [YYYY-MM-DD]"
```

### `--all` 다중 repo 그룹핑 커밋

`--all` 모드에서는 변경된 handbook 파일을 **git repo 루트 단위로 그룹핑**하여 repo별로 각각 커밋한다.

1. 반영에 성공한 파일 경로마다 `git rev-parse --show-toplevel`로 repo 루트를 구한다.
2. 같은 repo 루트를 가진 파일을 묶어 하나의 커밋으로 처리한다.
3. `.last_handbook_update`도 해당 repo에 속하면 함께 포함한다.

```bash
# repo-A 그룹
git -C {repo_root_A} add {repo_A_파일_목록} .last_handbook_update
git -C {repo_root_A} commit -m "docs: handbook update [$(date +%Y-%m-%d)]"

# repo-B 그룹 (별도 커밋)
git -C {repo_root_B} add {repo_B_파일_목록}
git -C {repo_root_B} commit -m "docs: handbook update [$(date +%Y-%m-%d)]"
```

```
커밋 (repo-A): <SHA> — "docs: handbook update [YYYY-MM-DD]"
커밋 (repo-B): <SHA> — "docs: handbook update [YYYY-MM-DD]"
```

### 공통 규칙

- **커밋 메시지**: `"docs: handbook update [YYYY-MM-DD]"` 형식으로 자동 생성한다. 날짜는 실행 시점의 로컬 날짜(`date +%Y-%m-%d`)를 사용한다.
- **스탬프 포함**: `.last_handbook_update` 파일이 해당 repo에 존재하면 커밋에 반드시 포함한다.
- **머지·푸시 없음**: `git commit`까지만 수행하며, `git push` 및 `git merge`는 절대 실행하지 않는다.
- **반영 0건 시 건너뜀**: 반영(갱신·신규 생성)이 0건이면 커밋을 실행하지 않는다.
- **dry-run 시 건너뜀**: `--dry-run`과 함께 지정된 경우 커밋도 건너뛴다.

---

# 연계 흐름

두 스킬은 독립 실행된다. 필요 시 아래 순서로 순차 실행한다.

```
1. /handbook-update → writable=true handbook 파일 갱신 (본 스킬)
2. /catalog-update  → _wiki 인덱스 생성·갱신
```

`handbook-update`는 handbook 파일 자체를 갱신하고, `catalog-update`는 갱신된 handbook 파일을 읽어 _wiki 인덱스를 생성한다. 순서를 반드시 지킨다.

`catalog-update` 스킬은 handbook 파일을 **읽기 전용**으로만 사용하며 수정하지 않는다. handbook 파일 갱신이 필요하면 반드시 `/handbook-update`를 먼저 실행한다.

## `--all --now --force` 조합 순서 예시

모든 프로젝트의 handbook을 즉시·강제 갱신하고 커밋한 뒤, 이어서 catalog 인덱스도 전체 재생성하는 전형적인 전체 갱신 흐름:

```
# 1단계: handbook 전체 갱신 (조건 무시, LOCK 외 강제 재작성, 커밋 포함)
/handbook-update --all --now --force --commit

# 2단계: catalog 인덱스 전체 재생성 (handbook 갱신 완료 후 실행)
/catalog-update --all --force --commit
```

- `--all`: 설정된 모든 프로젝트 순회
- `--now`: `update_when` 조건 무시, 스케줄과 무관하게 즉시 실행
- `--force`: LOCK 보호 영역 외 기존 내용 강제 재작성
- `--commit`: 각 스킬 완료 후 변경 파일을 repo별로 그룹핑하여 자동 커밋
- 순서 보장: handbook 갱신이 완전히 완료된 뒤 catalog를 실행해야 최신 handbook 내용이 인덱싱된다.

---

# 제약 조건

1. **writable=false이거나 문자열 형식인 handbook 항목은 읽기 전용 — 수정 절대 금지** (심층 방어 2차 — 프롬프트 규칙)

   - `handbook` 항목이 문자열 형식(예: `"README.md"`)이거나, 객체 형식이더라도 `writable: false`(또는 `writable` 키 미존재)인 경우, 해당 파일은 **스캔(읽기)만 허용**하며 Write·Edit 등 쓰기 도구 사용이 금지된다.
   - 반대로 **`writable: true`로 명시된 항목만이 쓰기(Edit/Write) 대상**이다. W-3에서 추출한 `writable=true` 목록에 없는 파일은 설령 존재하더라도 수정하지 않는다.
   - **신규 파일 Write도 `writable: true` 경로 한정**: W-6b의 신규 생성 흐름에서 Write 툴로 파일을 생성하는 경우도, `handbook`에 `writable: true`로 선언된 경로에만 허용된다. `writable: true`로 선언되지 않은 경로에 새 파일을 생성하지 않는다. 이 규칙은 1차 hook 방어(PreToolUse)와 정합된다.
   - **1차 방어(코드/하네스 레벨)**: PreToolUse hook(`settings.json`)이 Edit/Write/NotebookEdit 호출을 인터셉트하여, `file_path`가 현재 프로젝트의 `writable=false`(및 문자열 형식) handbook 경로 집합에 포함되면 **하네스 수준에서 자동 차단**한다. LLM의 규칙 준수 의지와 무관하게 결정적(deterministic)으로 동작한다.
   - **2차 방어(프롬프트 규칙 — 본 항목)**: 1차 hook이 미작동하거나 스코프 밖인 상황에서도 이 프롬프트 규칙이 추가 방어선으로 작동한다. "코드 1차 + 프롬프트 2차"의 심층 방어(defense in depth).

2. **LOCK 마커 보호 영역 수정 금지** — `<!-- LOCK:START -->` ~ `<!-- LOCK:END -->` 내부는 일절 수정·삭제 불가 (W-6 참조). `--force` 재작성 시에도 동일하게 적용된다.
3. **사용자 승인 전 파일 수정 금지** — LLM은 변경 내용을 제안하고 사용자가 승인한 뒤에만 파일을 수정한다 (W-7 참조)
4. `--dry-run` 시 파일 Write·Edit 금지 — 출력만 (`--now`/`--force`와 함께 지정해도 동일)
5. `--dry-run` 시 `.last_handbook_update` 갱신 금지
6. 승인 반영이 1건 이상 있을 때만 `.last_handbook_update` 갱신 (변경없음·전부거부·dry-run 시 건너뜀)
7. `update_when` 조건 불부합 시 해당 파일 갱신 제외 — 단, 스캔(읽기)은 수행 가능. `--now`/`--force` 시 이 규칙이 무효화된다.
8. `_wiki/*.md` 파일(T-xxx, D-xxx)은 이 스킬의 갱신 대상이 아님 — catalog-update 스킬 사용
9. **신규 생성은 `--now` 또는 `--force` 시에만**: 기본 증분 모드에서는 `writable: true` 파일이 디스크에 없어도 신규 생성하지 않는다.
10. **스탬프 부재·빈 파일·무효 SHA는 모두 전체 평가 폴백**: `.last_handbook_update` 파일이 없거나 내용이 비어 있거나, 기록된 SHA가 git 히스토리에 존재하지 않는 경우(강제 rebase·reset 후 등), `main` 브랜치 fallback 없이 **첫 실행과 동일한 전체 평가 모드로 폴백**한다. `update_when` 게이트는 통과 처리, 사용자 승인(W-7)은 유지.
11. **빈-diff 폴백은 스탬프 갱신 조건과 무관**: W-2 빈-diff 가드로 전체 평가 모드에 진입한 경우라도, 갱신 0건이면 스탬프를 기록하지 않는다(다음 실행도 전체 평가 재진입 — 의도된 동작).

---

# W-9. embed 단계 (자기완결 embed / defer 분기)

W-8 완료 직후(`.last_handbook_update` 갱신 이후) 실행한다. **실제로 반영(Edit/Write)된 handbook 파일만** 대상으로 한다.

## 갱신 0건 시

embed 단계를 완전히 생략한다. `EMBED_FILES:` 출력도 하지 않는다.

## `--dry-run` 시

embed 단계를 건너뛴다. `EMBED_FILES:` 출력도 하지 않는다.

## `--defer-embed` 없을 때 (단독 실행 — 자기완결 embed)

W-7에서 승인·반영된 handbook 파일 경로를 모아 아래 명령을 실행한다.

```bash
LOREGIST_AUTO_GUARD=1 loregist embed --file <갱신파일1> --file <갱신파일2> …
```

- `LOREGIST_AUTO_GUARD=1` 환경변수를 prefix로 붙여 embed → handbook-update 재귀 호출을 차단한다.
- `--file` 플래그를 갱신 파일 수만큼 반복하여 지정한다.
- `--all` 모드에서는 모든 프로젝트의 갱신 파일을 합산하여 한 번에 호출한다.

## `--defer-embed` 있을 때 (상위 wiki-update에 위임)

embed를 스킵하고, 갱신된 파일 목록을 다음 형식으로 표준 출력에 한 줄 출력한다.

```
EMBED_FILES: path1 path2 …
```

- 경로 구분자는 공백(스페이스)이다.
- 상위 `wiki-update` 스킬이 이 줄을 파싱하여 embed를 일괄 처리한다.
- 갱신 파일이 없을 때는 이 줄을 출력하지 않는다.

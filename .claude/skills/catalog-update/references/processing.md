## 목차

- [B-3a. handbook 스키마 해석](#b-3a-handbook-스키마-해석)
- [B-3. 스캔 소스 결정](#b-3-스캔-소스-결정)
- [B-4. LLM 분석](#b-4-llm-분석)
- [B-5. 중복 검사 (2단계)](#b-5-중복-검사-2단계)
- [B-5-force. --force 본문 재작성 보호 장치](#b-5-force---force-본문-재작성-보호-장치)
- [B-6. ID 자동 부여](#b-6-id-자동-부여)
- [B-7. 파일 작성](#b-7-파일-작성)
- [B-8. 완료 처리](#b-8-완료-처리)

---

# B-3a. handbook 스키마 해석

`stashdex project list --json` 으로 현재 프로젝트의 `handbook` 배열을 읽는다.
각 항목은 **문자열** 또는 **객체 `{path, writable, update_when}`** 두 가지 형식이 모두 올 수 있다.

## 항목 형식별 처리

이 스킬은 **모든 handbook 항목을 읽기 전용**으로 스캔한다. writable 값에 관계없이 파일 수정은 수행하지 않는다.

| 형식 | 예시 | 처리 방식 |
|---|---|---|
| 문자열 | `"etc/topology.md"` | 읽기 전용 — 스캔만 수행, 파일 수정 불가 |
| 객체 (`writable` 미지정 또는 `false`) | `{path: "etc/log.md", writable: false}` | 읽기 전용 — 스캔만 수행, 파일 수정 불가 |
| 객체 (`writable: true`) | `{path: "etc/handbook.md", writable: true, update_when: "..."}` | 읽기 전용 — 스캔만 수행, 파일 수정 불가 |

**handbook 파일 수정 금지** — 이 스킬은 handbook 파일을 읽기 전용으로만 사용한다. handbook 파일 갱신이 필요하면 `/wiki-update` 스킬을 실행한다.

> handbook 파일 쓰기·LOCK 보호 영역·사용자 승인·update_when 규칙은 `/wiki-update` 참조

---

# B-3. 스캔 소스 결정

## 1단계: handbook 확인

```bash
stashdex project list --json
```

결과에서 현재 프로젝트의 `handbook` 배열을 추출한다. 각 항목은 문자열 또는 `{path, writable, update_when}` 객체다 (B-3a 참조).

## 2단계: 소스 분기

> **`--now` 모드 시**: `.last_catalog_update` base를 **완전히 무시**한다. 아래 base SHA 결정 단계를 건너뛰고 "base 필터 없이 전체 스캔" 경로로 직행한다. 내부 스캔 경로는 B-1b(`--scan`) 경로를 재사용한다.

**handbook이 하나라도 있으면 → 1순위 (handbook 전체 스캔)**

handbook에 나열된 파일 전체를 스캔 대상으로 사용한다. diff 필터를 적용하지 않고 전체 스캔한다.
모든 항목은 B-3a 규칙에 따라 읽기 전용으로 처리한다.

**handbook이 비어 있으면 → 2~4순위 대체 소스 사용 (git diff 기반)**

### base SHA 결정 (첫 실행 마이그레이션 포함)

1. `_wiki/.last_catalog_update` 파일 읽기 (커밋 SHA 1줄)
   - **존재하면**: 해당 SHA를 base로 사용
   - **없고 구 `_wiki/.last_update`(타임스탬프)가 존재하면**: 그 날짜를 1회 base로 사용 후, 처리 완료 시 신규 SHA 마커(`_wiki/.last_catalog_update`)를 기록 (마이그레이션)
   - **둘 다 없으면**: base 필터 없이 전체 스캔

### git 추적 소스 (diff 기반 필터)

```bash
# base가 SHA인 경우
git diff <sha> HEAD --name-only

# base가 날짜인 경우 (마이그레이션)
git log --after=<날짜> --name-only --pretty=format:""
```

2. 2순위: `{docs_root}/{날짜}/` 작업문서 — base 이후 변경된 파일만 (`git diff` 필터 적용)
3. 3순위: `plans/done/` 완료 계획서 — base 이후 변경된 파일만 (`git diff` 필터 적용)

### 비git 소스 (mtime 기반 필터)

비git 소스인 `logvault`는 SHA로 직접 diff할 수 없으므로, SHA의 커밋 시각을 파생하여 mtime 비교한다.

```bash
# SHA에서 커밋 시각 파생
git show -s --format=%cI <sha>
```

4. 4순위: `logvault/{project}/*.log` — 파생된 커밋 시각 이후 mtime 파일만 스캔

---

# B-4. LLM 분석

## 섹션 분할

스캔 대상 각 파일을 `##` 기준으로 섹션 단위로 분할한다.

## topic vs decision 판별

각 섹션에 대해 아래 신호로 유형을 판별한다.

**topic 신호:**
- 반복 도메인 개념·기술 영역을 설명하는 내용
- 명사 중심 섹션 제목 (예: "인프라 구조", "배포 파이프라인")
- "개념/구조/현황/설계" 키워드 포함

**decision 신호:**
- 명시적 선택이 이루어진 결정 내용
- "결정/선택/정책/채택/확정" 키워드 포함
- "방안 A/B → A 선택", "~로 결정" 패턴

**판별 불가 / 카탈로그 가치 없음:** 스킵 (단순 로그·메모·연락처 등)

## 분석 결과 형식

| 항목 | 설명 |
|---|---|
| 후보명 | 카탈로그 항목 제목 (한국어 명사구) |
| type | `topic` 또는 `decision` |
| 소스 파일 | 원본 파일 경로 |
| 소스 섹션 | `##` 섹션 제목 |
| 요약 | 핵심 내용 1줄 요약 |

---

# B-5. 중복 검사 (2단계)

## 1단계: 인덱스 직독

`_wiki/TOPICS.md`·`_wiki/DECISIONS.md`를 읽어 기존 항목의 id와 title을 수집한다.
제목이 완전히 일치하면 중복으로 판정한다.

## 2단계: 시맨틱 검색

```bash
stashdex search <후보명>
```

결과에서 상위 1건의 유사도를 파싱한다. **유사도 > 0.85이면 중복 판정.**

## 중복 판정 시 처리

- 해당 기존 파일(`_wiki/T-xxx.md` 또는 `D-xxx.md`)의 frontmatter `related:` 리스트에 소스 파일명 추가 (Edit 툴 사용)
- 본문 덮어쓰기 금지
- 신규 파일 생성하지 않음

---

# B-5-force. `--force` 본문 재작성 보호 장치

`--force` 플래그가 지정되면 기존 `_wiki/*.md` 항목의 본문을 재생성할 수 있다. 단, 아래 **보호 장치를 모두 적용**한다. 하나라도 위반하면 해당 항목은 재작성 대상에서 제외한다.

## 재작성 제외 조건

### 1. `status: edited` 항목 제외

frontmatter에 `status: edited`가 있는 파일은 사용자가 직접 편집한 것으로 간주한다. 재작성 대상에서 제외하고 사유를 출력한다.

```
[force] T-003 건너뜀 — status: edited (사용자 편집 보호)
```

### 2. `_wiki/*.md` 본문 LOCK 마커 영역 보존

파일 본문 내 아래 마커 사이의 내용은 재작성하지 않는다.

```
<!-- LOCK:BEGIN -->
... 이 영역은 catalog-update --force 시에도 재작성하지 않음 ...
<!-- LOCK:END -->
```

LOCK 마커 영역이 있는 파일은 마커 외부 본문만 재생성하고, 마커 내부는 원문 그대로 유지한다.

### 3. frontmatter 보존 필드

재작성 시 아래 frontmatter 필드는 **원본 값을 그대로 유지**하고 덮어쓰지 않는다.

| 보존 필드 | 설명 |
|---|---|
| `tags` | 사용자 태그 |
| `related` | 연관 항목 목록 |
| `status` | 현재 상태값 |
| `id` | 카탈로그 ID |
| `date` | 최초 생성일 |

재생성 대상: **본문(frontmatter 이후 텍스트)** 및 `summary` 필드만.

### 4. 항목별(또는 프로젝트 단위) 승인 후에만 재작성

`--force` 실행 시, 재작성 대상 항목 목록을 먼저 출력하고 **사용자 승인을 요청**한다.

#### 예외 (플래그=사전 승인)

`auto_catalog_update`가 켜져 있으면 사용자 사전 승인으로 간주해 무인으로 진행한다(매 호출 승인 프롬프트 생략). 꺼져 있으면(기본) 종전 승인 흐름을 따른다.

> **우선순위**: 이 예외는 `writable=false` 코드레벨 차단(P5) 및 `update_when` 게이트보다 하위다 — 그 두 게이트는 `auto_catalog_update` 플래그와 무관하게 항상 우선한다.

```
[force] 본문 재작성 예정 항목:
  T-003 "배포 파이프라인 구조" — status: draft
  D-002 "DB 엔진 선택: PostgreSQL" — status: draft

재작성하시겠습니까? (모두/T-003만/취소)
```

- **모두**: 목록 전체 재작성
- **id 지정** (예: `T-003만`): 해당 항목만 재작성
- **취소**: 재작성 없이 신규 항목 생성만 수행

`--dry-run --force` 조합 시: 재작성 예정 목록만 출력하고 실제 파일 수정 없이 종료.

---

# B-6. ID 자동 부여

## topic ID

```bash
ls {docs_root}/_wiki/T-*.md
```

파일명에서 숫자 추출 → `max + 1` → 3자리 패딩

예: 기존 `T-001.md`, `T-002.md` → 신규 `T-003`

## decision ID

```bash
ls {docs_root}/_wiki/D-*.md
```

동일 로직. 예: `D-001`, `D-002`, ...

## 패딩 규칙

항상 3자리 패딩: `T-001`, `T-002`, ..., `T-099`, `T-100`, `T-101`

---

# B-7. 파일 작성

## 신규 파일 frontmatter 형식

```yaml
---
id: T-001
type: topic
date: 2026-06-19
status: draft
tags: []
related: []
edges: []
summary: "핵심 내용 한 줄 요약"
---
# 제목

> 소스: `파일명.md §섹션명`

본문 내용 (소스 파일·섹션 핵심 내용 요약)
```

- `date`: 오늘 날짜 (`date +%Y-%m-%d`)
- `status`: 항상 `draft`로 초기 생성
- `tags`: 빈 리스트로 초기화 (LLM이 관련 키워드 1~3개 제안 가능)
- `related`: 빈 리스트로 초기화
- `edges`: 빈 리스트로 초기화 (stashdex catalog --lint로 보강 유도)

## 기존 파일 related 업데이트

중복 판정된 기존 파일의 frontmatter `related:` 리스트에 소스 파일명만 추가.

```yaml
# 변경 전
related: []

# 변경 후 (예시)
related:
  - etc/인프라_접속정보.md
```

Edit 툴 사용. 본문(frontmatter 이후 내용) 덮어쓰기 금지.

---

# B-8. 완료 처리

## `--dry-run` 모드

파일 작성·`.last_catalog_update` 갱신을 건너뛰고 생성 예정 목록만 출력한다.

```
[dry-run] 생성 예정:
  T-003 (topic) — "배포 파이프라인 구조" ← etc/인프라_접속정보.md §배포
  D-001 (decision) — "DB 엔진 선택: PostgreSQL" ← plans/done/db-migration.md §결정 사항

[dry-run] 본문 재작성 예정 (--force):
  T-002 "인프라 구조" — status: draft

[dry-run] 중복 skip:
  "인프라 접속정보" → T-001 (유사도 0.92)

[dry-run] 건너뜀 (status: edited):
  T-005 "배포 정책" — 사용자 편집 보호

파일 작성 및 .last_catalog_update 갱신을 건너뛰었습니다.
```

## 표준 완료 절차

### 1단계: 파일 작성

신규 판정된 항목마다 Write 툴로 `_wiki/{id}.md` 생성.

### 2단계: 인덱스 재생성

```bash
stashdex catalog --project {project_key}
```

TOPICS.md·DECISIONS.md 인덱스를 재생성한다.

### 3단계: `.last_catalog_update` 갱신 (프로젝트별 조건부)

각 프로젝트의 `docs_root`가 **git 저장소인지 여부**에 따라 기록 방식을 분기한다.

**git 저장소인 경우:**

```bash
git -C {docs_root} rev-parse HEAD
```

결과(HEAD SHA 1줄)를 `_wiki/.last_catalog_update` 파일에 Write 툴로 기록한다.

**git 저장소가 아닌 경우:**

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
```

ISO 8601 타임스탬프를 `_wiki/.last_catalog_update` 파일에 Write 툴로 기록한다.

> `--all` 순회 시: 각 프로젝트마다 위 분기를 독립적으로 수행한다.

### 4단계: embed (`--defer-embed` 없을 때)

이번 실행에서 생성·갱신한 `_wiki/*.md` 파일 목록을 수집한다.

**갱신 0건이면 이 단계를 건너뛴다.**

**`--dry-run` 시 이 단계를 건너뛴다.**

#### `--defer-embed` **없을 때** (기본): 직접 embed 실행

```bash
LOREGIST_AUTO_GUARD=1 stashdex embed --file <경로1> --file <경로2> …
```

생성·갱신된 `_wiki/*.md` 파일 각각에 `--file <경로>` 인자를 붙여 실행한다.

#### `--defer-embed` **있을 때**: embed 스킵 + 경로 목록 출력

embed를 수행하지 않고 아래 형식으로 한 줄 출력만 한다.

```
EMBED_FILES: {docs_root}/_wiki/T-003.md {docs_root}/_wiki/D-001.md …
```

- 경로는 절대 경로로 출력한다.
- 갱신 파일이 없으면 이 줄을 출력하지 않는다.

---

### 5단계: git commit (`--commit` 플래그 시)

`--commit` 플래그가 지정된 경우, 변경된 `_wiki/*.md` 파일과 `.last_catalog_update`를 git commit한다.

#### 단일 프로젝트

```bash
git -C {docs_root} add _wiki/ _wiki/.last_catalog_update
git -C {docs_root} commit -m "catalog-update: {N}개 항목 생성/갱신 [$(date +%Y-%m-%d)]"
```

```
커밋: <커밋 SHA> — "catalog-update: {N}개 항목 생성/갱신 [YYYY-MM-DD]"
```

#### `--all` 다중 repo 그룹핑 커밋

`--all` 모드에서는 각 프로젝트의 `docs_root`가 서로 다른 git repo에 위치할 수 있으므로, **git repo 루트 단위로 그룹핑**하여 repo별로 각각 커밋한다.

1. 각 프로젝트 처리 후 해당 `docs_root`의 git repo 루트(`git -C {docs_root} rev-parse --show-toplevel`)를 구한다.
2. 같은 repo 루트에 속하는 프로젝트들의 변경 파일을 묶어 하나의 커밋으로 처리한다.
3. `.last_catalog_update` 파일도 해당 repo의 커밋에 포함한다.

```bash
# repo-A 그룹 (loregist, sub-proj 등 동일 repo)
git -C {repo_root_A} add {repo_A_catalog_파일_목록}
git -C {repo_root_A} commit -m "catalog-update: {N}개 항목 생성/갱신 [$(date +%Y-%m-%d)]"

# repo-B 그룹 (별도 repo의 프로젝트)
git -C {repo_root_B} add {repo_B_catalog_파일_목록}
git -C {repo_root_B} commit -m "catalog-update: {N}개 항목 생성/갱신 [$(date +%Y-%m-%d)]"
```

#### 공통 규칙

- **커밋 메시지**: `"catalog-update: {N}개 항목 생성/갱신 [YYYY-MM-DD]"` 형식으로 자동 생성한다. `{N}`은 신규 생성 + 본문 재작성 합산 건수이며, 날짜는 실행 시점의 로컬 날짜를 사용한다.
- **스탬프 포함**: `_wiki/.last_catalog_update` 파일이 존재하면 커밋에 반드시 포함한다.
- **머지·푸시 없음**: `git commit`까지만 수행하며, `git push` 및 `git merge`는 절대 실행하지 않는다.
- **변경 0건 시 건너뜀**: 신규 생성·본문 재작성이 0건이면 커밋을 실행하지 않는다.
- **dry-run 시 건너뜀**: `--dry-run`과 `--commit`이 함께 지정된 경우 commit을 수행하지 않는다.
- **git 저장소 아닌 docs_root**: git repo가 아닌 `docs_root`에는 commit 단계를 건너뛴다.

# 출력 형식

## 단일 프로젝트 완료 출력

```
## catalog-update 완료

프로젝트: {project_key}
스캔 소스: handbook ({N}개 파일) / 대체 소스 2~4순위
분석 섹션: {N}개
신규 생성: {N}개 (T-xxx {N}개, D-xxx {N}개)
본문 재작성: {N}개 (--force 적용)
건너뜀(edited): {N}개
중복 skip: {N}개 (related 업데이트)

### 생성 목록
- T-003 `_wiki/T-003.md` — "배포 파이프라인 구조"
- D-001 `_wiki/D-001.md` — "DB 엔진 선택: PostgreSQL"

### 본문 재작성 목록 (--force)
- T-002 `_wiki/T-002.md` — "인프라 구조" (summary·본문 재생성, frontmatter 보존)

### 중복 처리
- T-001 related 업데이트 — "인프라 접속정보" (유사도 0.92)

### 건너뜀 (보호)
- T-005 "배포 정책" — status: edited

인덱스 재생성 완료 (TOPICS.md, DECISIONS.md)
.last_catalog_update: <HEAD SHA 또는 타임스탬프>
```

## `--all` 전 프로젝트 집계 출력

각 프로젝트 처리 후 행을 출력하고, 전체 순회 완료 후 합산 집계를 표시한다.

```
## catalog-update --all 완료

| 프로젝트 | 신규 생성 | 본문 재작성 | 건너뜀(edited) | 중복 skip |
|---|---|---|---|---|
| loregist | 3 | 1 | 0 | 2 |
| myproject | 0 | 0 | 1 | 1 |
| infra-docs | (skip: _wiki 없음) | — | — | — |
| **합계** | **3** | **1** | **1** | **3** |

처리 프로젝트: 2개 / 건너뜀: 1개
```

# 연계 흐름

두 스킬은 독립 실행된다. 필요 시 아래 순서로 순차 실행한다.

```
1. /wiki-update   → writable=true handbook 파일 갱신 (wiki-update 스킬)
2. /catalog-update → _wiki 인덱스 생성·갱신 (본 스킬)
```

`catalog-update`는 handbook 파일을 **읽기 전용**으로만 스캔하며 수정하지 않는다. handbook 파일 갱신이 필요하면 `/wiki-update`를 먼저 실행한다.

## `--all --now --force` 조합 순서 예시

모든 프로젝트의 wiki를 즉시·강제 갱신하고 커밋한 뒤, 이어서 catalog 인덱스도 전체 재생성하는 전형적인 전체 갱신 흐름:

```
# 1단계: wiki 전체 갱신 (조건 무시, LOCK 외 강제 재작성, 커밋 포함)
/wiki-update --all --now --force --commit

# 2단계: catalog 인덱스 전체 재생성 (wiki 갱신 완료 후 실행)
/catalog-update --all --force --commit
```

- `--all`: 설정된 모든 프로젝트 순회
- `--now`: wiki-update에서 `update_when` 조건 무시, 즉시 실행 (catalog-update는 해당 없음)
- `--force`: 기존 `_wiki/*.md` 본문을 강제 재작성 (status: edited 항목 포함)
- `--commit`: 각 스킬 완료 후 변경 파일을 repo별로 그룹핑하여 자동 커밋
- 순서 보장: wiki 갱신이 완전히 완료된 뒤 catalog를 실행해야 최신 wiki 내용이 인덱싱된다.

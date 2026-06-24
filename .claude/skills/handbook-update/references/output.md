# handbook-update 출력 형식 및 연계 흐름

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

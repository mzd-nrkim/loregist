---
name: daily-rollup
description: 전 프로젝트 할 일을 통합하여 personal-work/daily/{date}.md로 생성. (슬랙 보고는 daily-report 사용)
argument-hint: [YYYY-MM-DD] [--project <key>]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# daily-rollup 스킬

> 슬랙 데일리 보고(아침/저녁)가 필요하면 `daily-report` 스킬 사용.

## 동작

1. `loregist project list` 파싱 → `docs_root != null` 프로젝트 목록 확보; `PERSONAL_WORK_ROOT` = `personal-work` 프로젝트의 `docs_root` 값
   ```bash
   PERSONAL_WORK_ROOT=$(loregist project list | python3 -c "import sys,json; d=json.load(sys.stdin); print(next(p['docs_root'] for p in d if p['name']=='personal-work'))")
   ```
2. `--project <key>` 인자가 있으면 해당 프로젝트만 처리
3. 각 프로젝트: `{docs_root}/{date}/{date}.01.작업문서.md` 파일에서 `## 오늘 할 일` 섹션 추출
4. `{PERSONAL_WORK_ROOT}/daily/{date}.md` 생성/갱신

## 출력 형식

```
<!-- ROLLUP:START -->
## loregist

- [ ] 항목1  ([원본 인덱스](../projects/loregist/dev/{date}/{date}.01.작업문서.md))
- [ ] 항목2

## {other-project}
...
<!-- ROLLUP:END -->
```

## 멱등성
- 파일이 이미 있으면 `<!-- ROLLUP:START -->`와 `<!-- ROLLUP:END -->` 마커 사이만 갱신
- 마커 밖 수동 메모 보존

## 인자
- `[YYYY-MM-DD]`: 기본값 오늘 날짜
- `--project <key>`: 특정 프로젝트만 처리

## 실행 절차
1. 날짜 결정 (인자 또는 오늘)
2. `loregist project list` 실행, 파싱; `PERSONAL_WORK_ROOT` 결정 (위 동작 1단계 참조)
3. 대상 프로젝트 순회:
   - `{docs_root}/{date}/` 디렉터리 탐색
   - `{date}.01.작업문서.md` 파일 읽기
   - `## {MM-DD} 오늘 할 일` 또는 `## 오늘 할 일` ~ 다음 `##` 전까지 추출
4. 섹션 조합 후 `{PERSONAL_WORK_ROOT}/daily/{date}.md` ROLLUP 영역 갱신

## 출력 파일 구조

파일이 없으면 아래 구조로 신규 생성한다:

```markdown
---
date: {YYYY-MM-DD}
updated: {YYYY-MM-DD HH:MM}
---
# {YYYY-MM-DD} 통합 할 일

<!-- ROLLUP:START -->
{프로젝트별 섹션}
<!-- ROLLUP:END -->
```

파일이 이미 있으면 ROLLUP 마커 사이만 교체하고 나머지 내용(수동 메모 등)은 보존한다.

## 프로젝트 해석

→ loregist/CLAUDE.md "스킬 공통 — 프로젝트 추론 규칙" 적용

## 제약 조건

1. 인덱스 파일이 없는 프로젝트는 해당 프로젝트 섹션에 `> 작업문서 없음` 표시 후 스킵
2. `docs_root`가 null인 프로젝트는 건너뜀
3. 기존 `personal-work/daily/{date}.md` 마커 밖 내용 절대 삭제 금지
4. `loregist project list` 실패 시 에러 출력 후 중단

---
name: future-plan
description: 미래 계획 문서 관리. 항목 조회(list), 추가(add), 데일리 작업으로 승격(promote)을 수행한다.
argument-hint: [list|add|promote] [주제명 또는 항목] [--project <key>]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# 경로 해석

`PERSONAL_WORK_ROOT` = `stashdex project list` 에서 `personal-work.docs_root` 값

```bash
PERSONAL_WORK_ROOT=$(stashdex project list | python3 -c "import sys,json; d=json.load(sys.stdin); print(next(p['docs_root'] for p in d if p['name']=='personal-work'))")
```

## 프로젝트 해석

→ loregist/CLAUDE.md "스킬 공통 — 프로젝트 추론 규칙" 적용

# 역할

`{PERSONAL_WORK_ROOT}/미래_계획.md` (전 프로젝트 횡단 파일)를 관리한다.
즉시 실행하지 않지만 조건 충족 시 데일리 작업으로 전환할 항목을 등록·조회·승격한다.

> **참고**: 이 스킬이 canonical 진입로(직접 처리). `/docs-manage future`는 docs-manager Agent 위임 경로 — 직접 호출 권장.

# 입력 분석

`$ARGUMENTS`를 파싱한다:

1. **액션** — 첫 번째 인자 (기본: `list`)
   - `list`: 미래 계획 항목 목록 출력 (선행 조건·승격 조건 포함)
   - `add <주제명>`: 새 항목 추가
   - `promote <주제명 또는 키워드>`: 항목을 오늘 데일리 작업으로 승격

2. **주제명/키워드** — 두 번째 인자 이후

3. **`--project <key>`**: 승격 시 대상 프로젝트의 docs_root 지정. 없으면 `stashdex project current`로 추론.

# 경로

| 구분 | 경로 |
|---|---|
| 미래 계획 | `{PERSONAL_WORK_ROOT}/미래_계획.md` (전 프로젝트 횡단) |
| 오늘 인덱스 | `{docs_root}/{YYYY-MM-DD}/{YYYY-MM-DD}.01.작업문서.md` |

# 액션별 처리

## list

1. `{PERSONAL_WORK_ROOT}/미래_계획.md`를 읽는다
   - 파일이 없으면 "미래 계획 파일이 없습니다: `{경로}`" 출력 후 종료
2. `## ` 레벨 섹션별로 요약 출력:
   - 주제명, 선행 조건, 승격 조건, 미완료 항목 수

출력 형식:
```
## 미래 계획 목록

| 주제 | 미완료 | 선행 조건 | 승격 조건 |
|---|---|---|---|
| {주제명} | {N}건 | {선행 조건 요약} | {승격 조건 요약} |
```

## add

1. `{PERSONAL_WORK_ROOT}/미래_계획.md`를 읽는다
   - 파일이 없으면 frontmatter + `# 미래 계획` 헤더로 신규 생성 후 진행
2. 문서 최하단에 새 섹션을 추가한다:

```markdown

## {주제명}

> 선행 조건: {대화 맥락에서 추출 또는 사용자 입력}
> 승격 조건: {대화 맥락에서 추출 또는 사용자 입력}

- [ ] {체크박스 항목들}
```

3. `updated` 타임스탬프를 갱신한다

## promote

1. `{PERSONAL_WORK_ROOT}/미래_계획.md`에서 키워드와 매칭되는 `## ` 섹션을 찾는다
2. 해당 섹션의 미완료 체크박스(`[ ]`)를 추출한다
3. `/add-work` 스킬과 동일한 방식으로 오늘 작업문서에 추가한다:
   - 인덱스에 소주제 + 체크박스 + 주제문서 링크
   - 주제별 문서 생성 (컨텍스트에 미래 계획 원본 참조)
   - "오늘 할 일"에 1줄 요약 추가
4. 미래 계획 문서에서 해당 섹션의 체크박스를 `[→]`로 변경하고 `(데일리 승격: YYYY-MM-DD)` 표기
5. `updated` 타임스탬프를 갱신한다

출력 형식:
```
## 미래 계획 → 데일리 승격 완료

- 주제: {주제명}
- 승격 항목: {N}건
- 주제별 문서: `{파일 경로}`
- 인덱스: `{인덱스 경로}` 에 소주제 추가
```

선행 조건이 명시된 경우 승격 전 경고 출력:
```
⚠ 선행 조건 `{내용}` — 충족 확인 후 진행하세요
승격을 계속하려면 확인을 요청한다.
```

# 제약 조건

1. **기존 내용 삭제 금지** — 추가/삽입/상태 변경만
2. **promote 시 선행 조건 확인** — 선행 조건이 명시되어 있으면 출력에 경고 표시 ("선행 조건 `{내용}` — 충족 확인 후 진행하세요")
3. CLAUDE.md의 작업 제안 금지 규칙 준수

---
name: catalog-update
description: handbook 파일을 스캔하여 _wiki/T-xxx.md(topic) / D-xxx.md(decision) 파일을 자동 생성·갱신한다. --now로 즉시 전체 스캔, --force로 기존 본문 재생성, --all로 전 프로젝트 순회.
argument-hint: [--project <key>] [--all] [--now [이름]] [--force] [--recommend-sources] [--dry-run] [--scan] [--commit]
allowed-tools: Agent, Bash, Read, Write, Edit, Glob, Grep
---

## 역할

오케스트레이터: 인자를 파싱하고 `catalog-update-core` 에이전트를 호출한다.

## 프로젝트 해석

1. `--project <key>` 인자가 있으면 그 프로젝트 사용
2. 없으면 `stashdex project current` (cwd 기준 자동 추론)
3. 추론 실패 시 사용자에게 프로젝트 키 질문

`docs_root`: 추론된 프로젝트의 docs_root 값 (`stashdex project list`로 확인)

→ stashdex/CLAUDE.md "스킬 공통 — 프로젝트 추론 규칙" 적용

이 스킬의 모든 상대 경로는 `{docs_root}/` 기준이다.

## 인수 정의

| 인수 | 설명 |
|---|---|
| `--project <key>` | 대상 프로젝트 키 명시 (생략 시 자동 추론) |
| `--all` | 전 프로젝트 순회 — `stashdex project list --json` 목록 전체에 대해 순차 실행 |
| `--now [이름]` | 즉시 전체 스캔 모드 — `.last_catalog_update` base 무시, 전체 스캔 강제 실행. `[이름]`을 지정하면 T-xxx/D-xxx id 또는 제목 매칭 항목만 처리. `--scan` 포섭: `--scan`과 동일한 스캔 경로를 수행하면서 게이트(base) 무시 + 누락 항목 생성까지 포함 |
| `--force` | 기존 T/D 항목 본문 재생성 포함 — 보호 장치 하 재작성 허용 (`--now` 또는 `--scan`과 함께 사용) |
| `--recommend-sources` | handbook 추천 모드 — 파일을 분석해 추가 여부를 사용자에게 확인 |
| `--dry-run` | 생성 예정 목록만 출력, 파일 작성·`.last_catalog_update` 갱신 건너뜀 |
| `--scan` | 코드·문서 직접 스캔 모드 — cold start나 drift 감지 시 사용. `--now` 없이 단독 사용 시 base 필터 적용. `--now`의 별칭 역할: `--scan` 단독 = 전체 스캔만, `--now`는 `--scan`을 포섭하여 게이트 무시+누락 생성까지 수행 |
| `--commit` | 완료 후 변경된 `_wiki/*.md` 파일을 git commit |
| `--defer-embed` | embed 단계를 스킵하고 `EMBED_FILES: <경로들>` 한 줄을 출력 — wiki-update 등 상위 오케스트레이터가 일괄 embed할 때 사용 |

## 처리 흐름

### 1단계: 인자 파싱 + 프로젝트 추론

수신된 인자를 파싱하고 위 프로젝트 해석 규칙에 따라 `docs_root`와 프로젝트 key를 추론한다.

### 2단계: Agent 도구로 `catalog-update-core` 호출

Agent 도구를 사용해 `catalog-update-core` 에이전트를 호출한다. 호출 프롬프트에는 다음을 포함한다:

- 추론된 `docs_root` 경로
- 추론된 프로젝트 key
- 전달된 인자 전체: `--project`, `--all`, `--now [이름]`, `--force`, `--recommend-sources`, `--dry-run`, `--scan`, `--commit`, `--defer-embed`
- `--all` 인자가 있으면 전체 프로젝트 목록과 각 `docs_root`도 함께 전달

### 3단계: 에이전트 완료 후 처리

에이전트 출력에서 다음을 파싱한다:

1. **`EDITED_FILES:` 줄 파싱** — 변경된 파일 목록 확인
2. **`git diff --stat` 출력** — dirty 상태 확인 (변경 사항 요약 표시)
3. **`COMMIT_REQUESTED` 신호 처리** — 신호가 있으면 다음 커밋 명령을 실행한다:

   ```bash
   git -C {docs_root} add _wiki/ _wiki/.last_catalog_update
   git -C {docs_root} commit -m "catalog-update: {N}개 항목 생성/갱신 [$(date +%Y-%m-%d)]"
   ```

   `--all` 다중 repo 시에는 `references/output.md`의 repo 그룹핑 커밋 절차를 따른다.

4. **embed 처리**:
   - `--defer-embed` 없고 `EDITED_FILES`에 파일이 있으면:
     ```bash
     STASHDEX_AUTO_GUARD=1 stashdex embed --file <경로1> --file <경로2> …
     ```
   - `--defer-embed` 있으면 에이전트가 출력한 `EMBED_FILES:` 줄을 그대로 출력한다.

# 트리거 키워드

- `catalog-update`, `카탈로그 업데이트`, `catalog update`
- `handbook 스캔`, `topic 추출`, `decision 추출`
- `카탈로그 생성`, `카탈로그 갱신`

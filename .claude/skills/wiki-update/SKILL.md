---
name: wiki-update
description: handbook(산문 문서)과 catalog(자동 증류 색인)을 순차 갱신하는 상위 오케스트레이터. handbook-update → catalog-update 순으로 호출해 wiki(= handbook + catalog) 전체를 최신 상태로 유지한다.
argument-hint: [--project <key>] [--all] [--dry-run]
allowed-tools: Agent, Bash, Read, Glob
---

## 역할

`wiki = handbook + catalog` 위계의 상위 오케스트레이터.

- **handbook**: 사람이 권위를 갖는 수동편집 가능 종합 문서 (README.md, ARCHITECTURE.md 등)
- **catalog**: handbook을 소스로 LLM이 자동 증류한 topic·decision 색인 (_wiki/)
- **wiki-update**: handbook을 먼저 갱신하고(handbook-update), 그 결과를 catalog에 반영(catalog-update)하는 순서를 보장한다.

```
wiki-update ⊃ { handbook-update → catalog-update }
              (증류 방향 = handbook 먼저, catalog 나중)
```

## 프로젝트 해석

1. `--project <key>` 가 있으면 그 프로젝트 사용
2. 없으면 `loregist project current` (cwd 기준 자동 추론)
3. 추론 실패 시 사용자에게 프로젝트 키 질문

## 처리 순서

### 1단계: handbook-update 호출

`/handbook-update [--project <key>] [--dry-run] --defer-embed` 를 수행한다.

- `--all` 이면 전 프로젝트 순회 (handbook-update에 `--all` 전파)
- `--dry-run` 이면 실제 파일 수정 없이 변경 예정 내용만 출력 (하위 스킬에 전파)
- `--project <key>` 를 명시한 경우 하위 스킬에 그대로 전파
- `--defer-embed` 를 전달해 handbook-update 내부의 개별 embed를 스킵하게 한다.
  handbook-update는 갱신한 파일 목록을 `EMBED_FILES: <공백구분 경로>` 한 줄로 출력한다.

### 2단계: catalog-update 호출

handbook-update 완료 후 `/catalog-update [--project <key>] [--dry-run] --defer-embed` 를 수행한다.

- handbook-update가 변경을 만들었거나 `--dry-run`이 아닌 경우에 실행
- `--dry-run` 이면 catalog도 dry-run으로 전파 (실제 _wiki/ 파일 미수정)
- `--project <key>` 를 명시한 경우 하위 스킬에 그대로 전파
- `--defer-embed` 를 전달해 catalog-update 내부의 개별 embed를 스킵하게 한다.
  catalog-update는 갱신한 파일 목록을 `EMBED_FILES: <공백구분 경로>` 한 줄로 출력한다.

### 3단계: 통합 embed 1회 호출

<!-- E-4: 두 하위 스킬의 EMBED_FILES 출력을 수집·중복 제거 후 단 1회 embed -->
<!-- E-5: 순환 가드 — LOREGIST_AUTO_GUARD=1 + --file 경로 지정 방식이므로
          embed가 drift→wiki-update 재기동을 유발하지 않는다(무한 재귀 차단).
          handbook/`_wiki` 커밋은 현재 post-commit hook이 embed로 안 잡지만,
          wiki-update 실행 자체가 임베딩을 수행하므로 대부분 무력화됨.
          hook 범위 확장은 별도 검토 사항(F-1 참고). -->

1단계·2단계에서 출력된 `EMBED_FILES:` 줄을 파싱해 경로를 합산하고 중복을 제거한다.

- 합산 경로 목록이 0건이면 embed 스킵.
- `--dry-run` 이면 embed 스킵 (출력만).
- 1건 이상이면 각 경로에 대해 아래를 실행한다:

```bash
LOREGIST_AUTO_GUARD=1 loregist embed --file <경로>
```

> **순환 가드**: `LOREGIST_AUTO_GUARD=1` 환경변수 + `--file` 개별 경로 지정 방식이므로,
> embed 완료 후 drift 감지 → wiki-update 재기동이 발생하지 않는다(무한 재귀 차단됨).

## 인자

| 인자 | 설명 |
|---|---|
| `--project <key>` | 대상 프로젝트 지정 (생략 시 자동 추론) |
| `--all` | 전 프로젝트 순회 |
| `--dry-run` | 실제 수정 없이 변경 예정 내용만 출력 |

## 트리거 키워드

- `wiki 전체 갱신`, `wiki 업데이트`, `wiki-update`
- `handbook과 catalog 모두 갱신`, `전체 wiki 최신화`
- "README랑 catalog도 같이 갱신해줘" 처럼 handbook+catalog 동시 요청

> handbook만 갱신이 필요하면 → `/handbook-update`
> catalog만 갱신이 필요하면 → `/catalog-update`

<!-- F-1: 트리거 갭 메모 -->
<!-- handbook 파일이나 `_wiki/` 디렉터리에 대한 커밋은 현재 post-commit hook이
     embed 대상으로 잡지 않는다. 그러나 wiki-update가 embed를 직접 포함(3단계)하므로
     wiki-update 실행 자체가 임베딩을 수행해 이 갭을 대부분 무력화한다.
     post-commit hook 범위를 handbook/`_wiki` 커밋까지 확장하는 것은 별도 검토 사항. -->

## 출력

```
[wiki-update] 프로젝트: <key>
  1/2 handbook-update ... 완료 (N개 파일 갱신)
  2/2 catalog-update  ... 완료 (M개 항목 갱신)
[wiki-update] 완료
```

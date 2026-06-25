# Claude Code 스킬 가이드

→ [README.md](../../README.md) / [ARCHITECTURE.md](../../ARCHITECTURE.md#claude-code-스킬)

stashdex는 Claude Code 스킬(`/skill-name`)을 통해 반복 업무를 자동화한다. 스킬은 두 가지 역할을 겸한다:

- **소비 레이어** — `stashdex search`로 과거 기록을 컨텍스트에 주입해 반복 작업 자동화
- **문서 작성 도우미** — 원시 텍스트(로그·메모)를 구조화된 문서로 변환하고, 그 문서에서 지식을 증류

## 호출 방법

Claude Code 터미널에서 슬래시 명령어로 실행한다.
슬래시 명령어 없이 Claude Code에 자연어로 말해도 동일하게 호출된다 — 예: "로그 처리해줘", "오늘 보고 만들어줘".

```bash
/process-history ./history.log
/add-work DB_스키마_변경 --done
/daily-report morning
/wiki-update --all
```

대부분의 스킬은 **프로젝트 자동 추론**을 지원한다 — cwd 기준으로 현재 프로젝트를 감지하며, `--project <key>`로 명시 가능.

---

## 텍스트 → 문서 → 지식 베이스 파이프라인

```
원시 텍스트 (*.log / *.md / *.txt)
  │
  ├─ /process-history  → 구조화된 작업문서 + 다음 할 일 제안
  └─ /add-work         → 오늘 작업문서에 항목 등록
          │
          ├─ /daily-report  → 슬랙 데일리 보고
          ├─ /carry-over    → 내일 이월 목록
          │
          ├─ /handbook-update  → README·ARCHITECTURE 자동 갱신
          └─ /catalog-update   → _wiki/ topic·decision 색인
                    ↑
              /wiki-update (위 둘 통합 실행)
```

---

## 스킬 상세

### 일별 흐름

---

#### `/process-history` — 로그 → 문서 + 다음 할 일

VM 작업 히스토리나 세션 로그 파일을 읽어 주제별 작업문서에 기입하고, 다음 할 일과 실행 명령어를 제안한다. 텍스트 기반 업무 방식의 핵심 스킬.

> **자연어 호출 예**: "이 로그 파일 처리해줘" 또는 "히스토리 분석하고 다음 할 일 알려줘"

```bash
/process-history ./session.log
/process-history ./history.log --topic=DB_마이그레이션
/process-history ./history.log --doc=2026-06-24.01.작업문서.md
```

| 인자 | 설명 |
|---|---|
| `<log-file-path>` | 읽을 로그 파일 경로 (필수) |
| `--topic=<경로\|주제명>` | 기입 대상 주제별 문서 명시 |
| `--doc=<경로>` | 인덱스(작업문서) 명시 |
| `--project <key>` | 프로젝트 키 명시 |

---

#### `/add-work` — 오늘 작업문서에 항목 등록

오늘 작업문서(`{docs_root}/{날짜}/01.작업문서.md`)에 새 업무 항목을 추가한다. 인덱스에는 체크박스+링크, 상세는 주제별 문서로 분리 생성한다.

> **자연어 호출 예**: "오늘 작업 목록에 DB 마이그레이션 추가해줘" 또는 "작업 항목 등록해줘"

```bash
/add-work DB_스키마_변경
/add-work PRD_검토 --done
/add-work API_설계 --date 2026-06-25
```

| 인자 | 설명 |
|---|---|
| `<주제명>` | 업무 항목 이름 (필수) |
| `--date YYYY-MM-DD` | 대상 날짜 (기본: 오늘) |
| `--done` | 생성 즉시 완료 처리 |
| `--project <key>` | 프로젝트 키 명시 |

---

#### `/carry-over` — 전일 미진행 항목 이월

전일(또는 지정일) 작업문서의 미완료 항목을 오늘 작업문서로 이월한다. 이월 항목에는 원본 날짜 태그를 붙이고, 전일 원본에도 이월 표기를 남긴다.

> **자연어 호출 예**: "어제 못 한 항목 오늘로 이월해줘" 또는 "미완료 항목 넘겨줘"

```bash
/carry-over
/carry-over 2026-06-23
/carry-over --dry-run
```

| 인자 | 설명 |
|---|---|
| `[YYYY-MM-DD]` | 소스 날짜 (기본: 직전 작업문서 자동 탐색) |
| `--dry-run` | 이월 대상 항목만 출력, 파일 수정 없음 |
| `--project <key>` | 프로젝트 키 명시 |

---

### 보고 생성

---

#### `/daily-report` — 슬랙 데일리 보고

아침/저녁 슬랙 데일리 보고를 자동 생성한다. 작업문서를 1순위 소스로 사용하고, Jira/git log는 보조로 참조한다.

> **자연어 호출 예**: "아침 데일리 보고 만들어줘" 또는 "저녁 보고 생성해줘"

```bash
/daily-report morning
/daily-report evening
/daily-report morning --copy
/daily-report morning --dual
```

| 인자 | 설명 |
|---|---|
| `morning\|evening` | 아침/저녁 모드 (기본: 13시 기준 자동 선택) |
| `--copy` | 생성 후 클립보드 복사 |
| `--dual` | 슬랙용 요약 + 상세 보고 2단계 생성 |
| `--team` | 팀 repo 커밋 포함 |
| `--no-ticket` | Jira 티켓 번호 생략 |
| `--init` | 작업문서 없으면 자동 생성 |
| `--project <key>` | 프로젝트 키 명시 |

---

#### `/daily-rollup` — 전 프로젝트 통합 할 일

등록된 전 프로젝트의 오늘 작업문서에서 할 일을 모아 `personal-work/daily/{date}.md`로 통합 생성한다.

> **자연어 호출 예**: "오늘 전 프로젝트 할 일 모아줘" 또는 "데일리 롤업 만들어줘"

```bash
/daily-rollup
/daily-rollup 2026-06-25
```

| 인자 | 설명 |
|---|---|
| `[YYYY-MM-DD]` | 대상 날짜 (기본: 오늘) |
| `--project <key>` | 특정 프로젝트만 처리 |

---

### 문서 관리

---

#### `/docs-manage` — 공통 문서 조회·갱신

`{docs_root}/../etc/` 하위 공통 문서(방화벽·인프라·운영 정보)를 조회하거나 갱신한다. docs-manager Agent에 위임해 처리한다.

> **자연어 호출 예**: "방화벽 현황 조회해줘" 또는 "인프라 문서 업데이트해줘"

```bash
/docs-manage firewall status
/docs-manage firewall update ServiceA ServiceB DEV O
/docs-manage infra update "DB SID 추가"
/docs-manage airflow status
```

| 도메인 | 설명 |
|---|---|
| `firewall` | 방화벽 경로 개통 현황 조회·갱신 |
| `infra` | 인프라 접속 정보 조회·갱신 |
| `airflow` | 운영 정보(Connection Pool·DAG 설정 등) 조회·갱신 |

---

#### `/future-plan` — 미래 계획 관리

즉시 실행하지 않지만 조건 충족 시 데일리 작업으로 전환할 항목을 관리한다. `personal-work/미래_계획.md`가 대상 파일이다.

> **자연어 호출 예**: "미래 계획 목록 보여줘" 또는 "STG 연동 완료되면 할 일 등록해줘"

```bash
/future-plan list
/future-plan add "STG 환경 연동 완료 후 부하 테스트"
/future-plan promote "STG 환경 연동"
```

| 액션 | 설명 |
|---|---|
| `list` | 항목 목록 + 선행 조건 출력 (기본) |
| `add <주제명>` | 새 항목 추가 |
| `promote <키워드>` | 항목을 오늘 데일리 작업으로 승격 |

---

### 지식 증류

---

#### `/handbook-update` — 산문 문서 자동 갱신

git diff 기반으로 stale 섹션을 판단해 `writable=true`로 설정된 handbook 파일(README.md, ARCHITECTURE.md 등)을 섹션 단위로 갱신한다. 코드 변경이 생기면 문서가 자동으로 따라온다.

> **자연어 호출 예**: "README 최신 상태로 갱신해줘" 또는 "문서 업데이트해줘"

```bash
/handbook-update
/handbook-update --now
/handbook-update --force
/handbook-update --all --commit
/handbook-update --file ARCHITECTURE.md
```

| 인자 | 설명 |
|---|---|
| `--now [이름]` | 게이트 무시하고 즉시 갱신. `[이름]` 지정 시 해당 파일만 처리 |
| `--force` | `--now` 포함. LOCK 외 전 섹션 재작성 |
| `--all` | 전 프로젝트 순회 |
| `--commit` | 갱신 후 git commit 자동 실행 |
| `--dry-run` | stale 섹션 목록만 출력, 파일 수정 없음 |
| `--file <path>` | 특정 파일만 대상 처리 |
| `--fix-only` | 오류·불일치만 최소 수정 |

---

#### `/catalog-update` — topic·decision 자동 증류

handbook 파일을 스캔해 `_wiki/T-xxx.md`(topic) / `D-xxx.md`(decision) 파일을 자동 생성·갱신한다. LLM이 문서에서 핵심 주제와 결정을 추출해 색인화한다.

> **자연어 호출 예**: "위키 색인 갱신해줘" 또는 "topic·decision 추출해줘"

```bash
/catalog-update
/catalog-update --now
/catalog-update --force --all
/catalog-update --recommend-sources
/catalog-update --dry-run
```

| 인자 | 설명 |
|---|---|
| `--now [이름]` | `.last_catalog_update` 무시, 즉시 전체 스캔 |
| `--force` | 기존 T/D 항목 본문 재생성 포함 |
| `--all` | 전 프로젝트 순회 |
| `--recommend-sources` | 추가할 handbook 소스 추천 |
| `--dry-run` | 생성 예정 목록만 출력 |
| `--commit` | 갱신 후 git commit 자동 실행 |

**산출물:**
```
{docs_root}/_wiki/
├── TOPICS.md       # topic 인덱스 (자동 갱신)
├── DECISIONS.md    # decision 인덱스 (자동 갱신)
├── T-001.md        # topic 파일 (LLM 작성)
└── D-001.md        # decision 파일 (LLM 작성)
```

---

#### `/wiki-update` — handbook + catalog 통합 갱신

`handbook-update → catalog-update` 순서를 보장하는 상위 오케스트레이터. 두 스킬을 따로 실행할 필요 없이 한 번에 wiki 전체를 최신 상태로 유지한다.

> **자연어 호출 예**: "위키 전체 업데이트해줘" 또는 "handbook이랑 catalog 다 갱신해줘"

```bash
/wiki-update
/wiki-update --all
/wiki-update --dry-run
```

| 인자 | 설명 |
|---|---|
| `--all` | 전 프로젝트 순회 |
| `--dry-run` | 실제 파일 수정 없이 변경 예정 내용만 출력 |
| `--project <key>` | 프로젝트 키 명시 |

---

## 스킬 선택 가이드

| 상황 | 스킬 |
|---|---|
| VM/서버 작업 후 로그 파일이 있다 | `/process-history` |
| 오늘 할 일을 작업문서에 등록하고 싶다 | `/add-work` |
| 어제 못 끝낸 일을 오늘로 옮기고 싶다 | `/carry-over` |
| 슬랙 데일리 보고 초안을 만들고 싶다 | `/daily-report morning\|evening` |
| 전 프로젝트 할 일을 한눈에 보고 싶다 | `/daily-rollup` |
| 방화벽/인프라 정보를 조회하거나 갱신하고 싶다 | `/docs-manage` |
| 나중에 할 일을 기록해 두고 싶다 | `/future-plan add` |
| 코드 변경 후 README/ARCHITECTURE를 업데이트하고 싶다 | `/handbook-update --now` |
| 문서에서 핵심 결정·주제 색인을 만들고 싶다 | `/catalog-update` |
| handbook과 catalog를 한 번에 갱신하고 싶다 | `/wiki-update` |

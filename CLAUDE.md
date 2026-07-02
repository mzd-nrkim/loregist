# stashdex — 개인 repo 문서·로그 컨텍스트 검색 인프라

LLM이 repo 전체를 무차별 Grep/Glob 탐색하지 않도록, **검색 계층(Hot 파일 → Cold vector DB → vault)** 으로 컨텍스트 우선순위를 부여하는 중앙 도구. 작업 로그·문서를 repo 밖으로 빼서 검색 노이즈를 구조적으로 제거하고, 과거 이력은 시맨틱 검색으로 소환한다.

> 이 디렉터리는 **repo 밖 중앙 인프라**다(`~/workspace/stashdex/`). 각 프로젝트 repo는 CLAUDE.md 규칙 + `stashdex` 호출만 갖고, DB·venv·모델·스크립트는 여기 1벌만 둔다.

## 검색 계층 (설계 핵심)

```
1순위: docs/dev/{오늘}/ + docs/etc/   ← 파일 직접 읽기 (Hot)
2순위: stashdex search "쿼리"         ← 과거 이력 시맨틱 검색 (Cold, pgvector)
3순위: ~/workspace/logvault/       ← 원본 필요 시 경로 지정 수동 접근
```

- `.gitignore`로는 Claude의 파일시스템 직접 읽기를 막을 수 없고, CLAUDE.md 규칙은 soft boundary라 구조적 보장이 안 된다. **진짜 해결은 cold 파일을 repo 밖으로 빼는 것.**
- 각 repo의 CLAUDE.md에는 "문서·로그 컨텍스트" 규칙 블록이 들어가 있다(`*.log`, `cold/**` 기본 제외 + 과거 이력은 `stashdex search`로).

## 멀티 프로젝트 설계 ("최소 멀티")

retrofit 비용이 큰 레이어만 멀티로 반영하고, 운영 UX는 단일로 유지한다.

| 레이어 | 방침 |
|---|---|
| DB 스키마 | **멀티** — `project` 컬럼 (나중에 넣으면 전체 재임베딩) |
| 인프라 위치 | **중앙화** — 이 디렉터리에 DB/venv/모델/스크립트 1벌 |
| vault 경로 | **멀티** — `logvault/{project}/` |
| 검색 스코프(UX) | **단일** — 기본 cwd 기준 현재 프로젝트. 크로스는 `--all-projects` |

- `project` = config.py PROJECTS dict의 key. cwd/대상 경로에서 자동 추론(`infer_project`), `--project`로 override.
- 새 프로젝트 추가는 `projects.toml`에 `[projects.{키}]` 블록 추가 (코드 편집 불필요).

### 현재 PROJECTS 구조

| project | docs_root | vault | cold | done |
|---|---|---|---|---|
| stashdex-proj | `personal-work/projects/stashdex-proj/dev` | `logvault/stashdex-proj` | `logvault/stashdex-proj/cold` | (없음) |
| stashdex-proj2 | `personal-work/projects/stashdex-proj2/dev` | `logvault/stashdex-proj2` | `logvault/stashdex-proj2/cold` | (없음) |
| stashdex | (없음) | `logvault/stashdex` | (없음) | `stashdex/plans/done` |
| util | (없음) | `logvault/util` | (없음) | `tools/util/plans/done` |
| personal-work | `personal-work` | (없음) | (없음) | (없음) |

모든 경로는 `~/workspace/` 기준 상대경로.

키 의미: `cold` = embed만(rotate 비대상, cold storage 종착지) / `done` = embed + rotate 대상(파일명 날짜 기준 7일 후 vault/cold/ 이동)

## 구성

| 파일 | 역할 |
|---|---|
| `projects.toml` | 프로젝트 레지스트리 단일 소스 — `[projects.<키>]` 블록으로 온보딩/오프보딩 |
| `src/stashdex/config.py` | DB 접속·모델·`projects.toml` 로드·해석(`load_projects`) → `PROJECTS` dict 빌드, `infer_project()`, `get_db_connection()` |
| `src/stashdex/chunking.py` | `hash_file/hash_chunk`, `split_md`(`##`/`###` 기준), `split_log`(빈 줄 기준). MIN 100 / MAX 1500자 merge·split |
| `src/stashdex/embed.py` | 파일 스캔 → 원문 upsert → 청크 임베딩 → `doc_chunks` insert |
| `src/stashdex/search.py` | 쿼리 임베딩 → cosine top-k (`WHERE project=` 스코프) |
| `src/stashdex/tui.py` | TTY 출력 UX — 단계별 braille 스피너 + 색상 멀티라인 카드 + 번호 입력 기본앱 오픈. 비-TTY에선 전부 off |
| `src/stashdex/rotate.py` | repo docs/dev/ → vault 이동 (라이프사이클 관리) |
| `stashdex` | PATH 래퍼: `embed` / `search` / `projects` / `rotate` 서브커맨드 (`STASHDEX_CWD`로 호출 위치 전달) |
| `infra/docker-compose.yml` | pgvector 컨테이너 (port 5433, Airflow metaDB와 분리) |
| `infra/init.sql` | `doc_originals` / `doc_chunks` 스키마 + ivfflat·project 인덱스 |

## 스택

- **DB**: PostgreSQL 16 + pgvector, port **5433**, db/user `stashdex`/`stashdex`. 중앙 1 인스턴스를 모든 프로젝트가 `project` 컬럼으로 공유.
- **임베딩 모델**: `dragonkue/multilingual-e5-small-ko-v2` (384 dims, ~450MB, 한국어 특화 fine-tune). `models/`에 캐시 1벌.
- **Python**: 3.11 (`.python-version`), venv는 `.venv/`. `requirements.txt` / `requirements-dev.txt`.

## 명령어

```bash
stashdex search "stashdex 임베딩 현황"       # 현재 프로젝트 시맨틱 검색 top-5 (default: hybrid mode)
stashdex search "쿼리" --top-k 10 --min-score 0.85
stashdex search "쿼리" --all-projects       # 크로스 프로젝트
stashdex search "쿼리" --no-fallback        # 0건이어도 전체 재검색 안 함 (기본은 자동 fallback)
stashdex search "쿼리" --json               # JSON 구조화 출력 (스크립팅용)
stashdex search "쿼리" --plain              # TTY에서도 기존 한 줄 포맷 강제
stashdex search "쿼리" --open 1             # 1번 결과를 즉시 기본 앱으로 열기 (루프 없음)
stashdex search "쿼리" --no-interactive     # 색상 카드만 출력, 오픈 프롬프트 생략
stashdex embed                              # 현재 프로젝트 전체 임베딩 (멱등)
stashdex embed --dry-run                    # 대상 파일 목록만
stashdex project list                       # 전체 프로젝트 목록 JSON
stashdex project current                    # cwd 기준 현재 프로젝트 키
stashdex rotate --dry-run                   # 7일 초과 날짜폴더 → vault 이동 대상 미리보기
stashdex rotate --project stashdex          # 실이동 (임베딩된 것만, vault 삭제 안 함)

make test-unit       # DB 불필요 단위 테스트
make test-int        # pgvector 기동 전제 통합 테스트
make test-all        # 전체 + 커버리지
make embed-dry       # stashdex dry-run
make rotate-dry      # 현재 rotate 대상 미리보기
make db-up           # pgvector 컨테이너 기동
make db-down         # pgvector 컨테이너 중지

docker compose -f infra/docker-compose.yml up -d   # DB 기동
```

## 새 프로젝트 추가

1. `~/workspace/tools/personal-work/projects/{p}/` 디렉터리 생성 (`dev/`, `etc/` 하위)
2. `projects.toml`에 `[projects.{p}]` 블록 추가 (경로는 `~/workspace` 기준 상대경로, 없는 항목은 생략하면 `None`):
   - docs_root + vault + cold 타입 (stashdex 형):
     ```toml
     [projects.{p}]
     docs_root = "tools/personal-work/projects/{p}/dev"
     vault     = "logvault/{p}"
     cold      = "logvault/{p}/cold"
     catalog   = true
     ```
   - vault + done 타입 (stashdex·util 형, plans 폴더 rotate):
     ```toml
     [projects.{p}]
     vault = "logvault/{p}"
     done  = "stashdex/{p}/plans/done"
     ```
3. catalog opt-in(`catalog = true`)을 추가한 경우, `_wiki/` 초기화 실행:
   ```bash
   stashdex catalog-init --project {p}
   ```
   → `{docs_root}/_wiki/TOPICS.md`·`DECISIONS.md`가 생성된다.
   이후 `stashdex catalog --project {p}`(또는 post-commit 훅)으로 자동 갱신.
4. `stashdex embed --project {p}` 로 초기 임베딩

오프보딩: `projects.toml`에서 블록 삭제 + `stashdex embed` (또는 `DELETE FROM doc_originals WHERE project='{p}'`)

## 작업 규칙

### 1. cross-repo 경로 모호 시 전역 탐색 전에 질문 먼저

계획서·파일 경로가 상대경로로 주어졌을 때, cwd 기준 탐색 실패 후 `find /Users/...` 전역 탐색으로 즉시 넘어가지 않는다.
전역 탐색은 30초 이상 걸리고 불필요한 결과를 쏟아낸다.
"어느 repo/디렉터리에 있는 파일인가요?" 한 줄 질문 → 답변 후 정확한 경로로 바로 접근한다.

### 2. 계획서 작성 전 핵심 전제 확인

계획서 초안 작성 전, 다음 3가지가 불명확하면 먼저 확인한다:
- 대상: 이 계획이 적용될 사용자/시스템은 누구인가
- UX 제약: 비개발자 대상인가, 대화형인가, CLI인가
- 연계 컴포넌트: 함께 바뀌어야 하는 스킬·설정·파일이 무엇인가

확인 없이 초안을 쓰면 3~4회 수정이 반복된다 — 한 번 질문하는 것이 더 빠르다.

### 3. public repo git 트리 검증은 refs/heads/main 범위로 한정

public repo(stashdex)의 민감 정보 잔존 여부를 검증할 때 `git log --all` / `git grep --all`을 쓰지 않는다.
`--all`은 remote 추적 브랜치(refs/remotes/...)를 포함해 dev repo 이력이 섞여 오탐을 낸다.
검증 범위를 항상 `refs/heads/main` 또는 `HEAD`로 명시한다:

```bash
git grep "패턴" HEAD
git log HEAD --oneline -20
```

### 4. 계획서 정리 시 plan-cleanup 스킬 먼저 호출

plans/ 디렉터리를 정리할 때 `mv` / `rm` 직접 실행 전에 plan-cleanup 스킬을 먼저 호출한다.
plan-cleanup은 이동·재임베딩·중복 탐지를 자동 처리한다.
스킬이 커버하지 못하는 케이스(이중 중첩 디렉터리, untracked 파일 등)에만 수동 개입한다.

### 5. ⚠️ wiki-update 대상(handbook·catalog 자동생성물)은 사용자 동의 없이 직접 수정 금지

**`wiki-update`/`handbook-update`/`catalog-update` 스킬이 관리하는 파일은 에이전트(메인·서브 무관)가 직접 Edit/Write 하지 않는다.** 갱신이 필요하면 **반드시 해당 스킬을 통해** 수행하고, 스킬을 우회한 직접 편집은 **사용자 동의를 먼저 받는다**.

대상:
- **handbook(산문 문서)**: `projects.toml`의 `writable=true` 파일 — `docs/public/catalog-guide.md`, `README.md`, `ARCHITECTURE.md` 등. → `handbook-update` 스킬로 갱신.
- **catalog 자동생성물**: `docs/public/_wiki/T-*.md`·`D-*.md`·`TOPICS.md`·`DECISIONS.md`. → `catalog-update`(catalog_gen) 스킬로 갱신.

이유: 이 파일들은 스킬이 **git diff 기반 stale 판정·LLM distill**로 생성·갱신한다. 직접 손으로 고치면 (1) stale 판정 스탬프(`.last_handbook_update`)와 어긋나 다음 평가가 오판정되고, (2) 다음 재생성 때 덮어써지며, (3) catalog는 소스(plans/done·handbook)에서 다시 distill되므로 수동 편집이 무의미하다.

**계획서가 "섹션 추가" 같은 콘텐츠 변경을 지시하더라도, 그 실행 수단은 직접 편집이 아니라 스킬 실행이다.** plan/plan-run 등에서 이 대상의 콘텐츠 변경을 Phase로 위임할 때도, 위임 내용은 "**스킬 실행**"이어야 하며 "마크다운 직접 Edit"를 위임해서는 안 된다.

### 6. 기존 자동화의 동작은 코드·계획서 완독 후에만 단정한다 (특히 "실패한다")

`publish.sh`·`audit.sh`·스킬 등 **기존 자동화의 동작을 단정하기 전에 해당 코드 경로를 끝까지 읽는다.** 특히 **"이 도구는 X 때문에 실패한다"는 부정 결론**은 관련 분기·함수를 전부 확인한 뒤에만 낸다.

실제 사고(2026-06-24 발행): `publish.sh` tree-sync를 부분만 읽고(자동제외 로직 `273~330` 구간 건너뜀) "_wiki 고객명 때문에 발행이 반드시 실패한다"고 단정 → 사용자에게 불필요한 전략 질문·장문 분석을 출력. 실제로는 `_wiki` audit 위반 파일 **자동 제외**가 이미 구현·문서화(`plans/done/2026-06-23.공개발행_차단해소_*`)돼 있었고, 사용자가 *"치환하기로 했는데, 그 계획서는 없어?"*로 교정했다.

재발 방지:
- **발행·파이프라인 작업 착수 시 `plans/done`에서 해당 주제 계획서를 먼저 검색**해 설계 의도·기존 결정을 파악한 뒤 분석한다(코드만 보고 설계 의도를 역추론하지 않는다).
- 자동화의 핵심 로직(게이트·제외·롤백 분기)은 **부분 읽기 후 결론 금지** — 진입부터 종료 분기까지 읽고 단정한다.

## 규칙·주의

- **출력 UX (TTY 색상 카드/스피너/기본앱 오픈)**: TTY에서는 색상 멀티라인 카드·단계별 braille 스피너·번호 입력 오픈 프롬프트(루프)가 자동 활성화. 비-TTY(파이프·리다이렉트·pytest)에서는 기존 한 줄 `|` 포맷 유지. `--json` = 구조화 출력, `--plain` = TTY 강제 한 줄, `--open N` = N번 즉시 열기, `--no-interactive` = 프롬프트 생략. `NO_COLOR` 환경변수 존중, `STASHDEX_FORCE_COLOR`로 강제 가능.
- **e5 prefix 필수**: 임베딩 시 `passage: `, 쿼리 시 `query: ` 접두사를 붙인다(`embed_documents` / `embed_query`). 빼면 검색 품질 저하.
- **검색 모드**: 기본 `hybrid`(RRF 융합)가 vector·fts 단독보다 종합 우월(골든셋 80% vs 40%/60%). **약어·정확 키워드**(프로젝트 코드명 등)는 vector 의미검색으로 안 잡히니 `hybrid`/`fts`를 쓴다. RRF `rrf_k`는 10~100에서 적중률 차이 없어 기본 60 유지(측정 근거: golden-queries.yaml + `stashdex search --eval`).
- **검색 0건 fallback**: 현재 프로젝트 스코프가 0건이면 자동으로 `--all-projects` 재검색(stderr 안내 + `(전체, fallback)` 헤더). 빈 스코프(임베딩 0건 프로젝트)에서 특히 유용. `--no-fallback`으로 끈다.
- **멱등 임베딩**: `upsert_original`은 `ON CONFLICT (project, source_path)` UPDATE, `insert_chunks`는 해당 source의 청크를 DELETE 후 재삽입. 재실행해도 originals 수 불변.
- **원문 보존**: `doc_originals.full_text`에 전문 보관 → vault 삭제 후에도 복원 가능. DB가 1차 검색 계층.
- **임베딩 대상**: vault `*.log` + `cold/*.md`(rglob) + `done/*.md`(rglob) + `docs/dev/*/*.md`(날짜 폴더). **오늘 폴더·`_wiki`는 docs_root 스캔에서 제외**. (TODO: A 완료 시 catalog 임베딩 포함 방향으로 전환 예정 — plans/2026-06-19.컨텍스트관리_catalog_vault_후속계획.md A-3 참조)
- **라이프사이클**:
  - `docs_root/{YYYY-MM-DD}/` 폴더가 7일 초과 + 임베딩 완료 → `stashdex rotate`로 `vault/{날짜}/` 이동(repo git rm). 매주 월 09:00 launchd 자동 실행(`scripts/rotate-all.sh`).
  - `plans/done/` 내 `YYYY-MM-DD*.md` 파일이 7일 초과 + 임베딩 완료 → `vault/cold/` 이동(repo git rm). 파일명 날짜 기준.
  - **`cold` 키 경로는 rotate 비대상** — 이미 cold storage 종착지. embed만 대상.
- **기업망 SSL**: `src/stashdex/config.py` 상단에서 httpx `verify=False` 패치(HuggingFace 다운로드용 SSL inspection 우회). 모델 1회 워밍 후엔 로컬 캐시 사용.
- **rotate 경계조건**: `elapsed < ROTATE_TO_VAULT_DAYS` (`<=` 아님). 7일 이상이면 대상.
- **done_targets early return**: `if not targets and not done_targets:` — 두 조건 모두 비어야 early return. 하나만 체크하면 done rotate가 무시됨.

## 계획서 / 작업 이력은 여기에 두지 않는다

- **진행 중·미완료 계획**은 `plans/`에 있다. 후속 작업(FTS/hybrid, 자동 갱신, 라이프사이클, `_wiki`/OKF 차용 등)의 상세·착수 조건은 그쪽을 참조. CLAUDE.md에 복제하지 않는다(낡고, 자기 설계와 모순).
- **완료된 계획·수정보고서·트러블슈팅**은 `plans/done/`으로 저장한다. 임베딩 대상(`done.rglob("*.md")`)이므로 7일 후 vault 이동 후에도 `stashdex search`로 검색 가능. 과거 결정·이력이 궁금하면 파일을 훑지 말고 먼저 검색할 것.
- **가이드성 문서** (라이프사이클 정리·설계 결정 등)는 `docs/`에 영구 보관하고 관련 내용을 CLAUDE.md에 반영한다. `docs/`는 임베딩·rotate 대상이 아님(CLAUDE.md가 단일 참조점). **공개 문서는 `docs/public/`에, 그 외 `docs/`는 내부 전용(publish·audit 차단)**.
- CLAUDE.md는 **안정 지침만** 담는다(아키텍처·명령어·규칙). 단발 상태값(임베딩 건수 등)은 DB에서 직접 확인.

## 설계 철학 (안정)

다량·고볼륨 원시 기록(로그·일일 작업문서) → stashdex(검색 랭킹). 소수의 정제 지식(decision/topic) → OKF식 frontmatter catalog. 둘은 경쟁이 아니라 **파이프라인의 두 끝**이다.

## 롤백

`docker compose -f infra/docker-compose.yml down -v`. vault 원본과 `doc_originals.full_text`가 남아 있어 데이터 손실 없이 재구축 가능.

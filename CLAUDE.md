# loregist — 개인 repo 문서·로그 컨텍스트 검색 인프라

LLM이 repo 전체를 무차별 Grep/Glob 탐색하지 않도록, **검색 계층(Hot 파일 → Cold vector DB → vault)** 으로 컨텍스트 우선순위를 부여하는 중앙 도구. 작업 로그·문서를 repo 밖으로 빼서 검색 노이즈를 구조적으로 제거하고, 과거 이력은 시맨틱 검색으로 소환한다.

> 이 디렉터리는 **repo 밖 중앙 인프라**다(`~/workspace/loregist/`). 각 프로젝트 repo는 CLAUDE.md 규칙 + `loregist` 호출만 갖고, DB·venv·모델·스크립트는 여기 1벌만 둔다.

## 검색 계층 (설계 핵심)

```
1순위: docs/dev/{오늘}/ + docs/etc/   ← 파일 직접 읽기 (Hot)
2순위: loregist search "쿼리"         ← 과거 이력 시맨틱 검색 (Cold, pgvector)
3순위: ~/workspace/logvault/           ← 원본 필요 시 경로 지정 수동 접근
```

- `.gitignore`로는 Claude의 파일시스템 직접 읽기를 막을 수 없고, CLAUDE.md 규칙은 soft boundary라 구조적 보장이 안 된다. **진짜 해결은 cold 파일을 repo 밖으로 빼는 것.**
- 각 repo의 CLAUDE.md에는 "문서·로그 컨텍스트" 규칙 블록이 들어가 있다(`*.log`, `cold/**` 기본 제외 + 과거 이력은 `loregist search`로).

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
| project-a | `personal-work/projects/project-a/dev` | `logvault/project-a` | `logvault/project-a/cold` | (없음) |
| project-b | `personal-work/projects/project-b/dev` | `logvault/project-b` | `logvault/project-b/cold` | (없음) |
| loregist | (없음) | `logvault/loregist` | (없음) | `loregist/plans/done` |
| util | (없음) | `logvault/util` | (없음) | `tools/util/plans/done` |
| personal-work | `personal-work` | (없음) | (없음) | (없음) |

모든 경로는 `~/workspace/` 기준 상대경로.

키 의미: `cold` = embed만(rotate 비대상, cold storage 종착지) / `done` = embed + rotate 대상(파일명 날짜 기준 7일 후 vault/cold/ 이동)

## 구성

| 파일 | 역할 |
|---|---|
| `projects.toml` | 프로젝트 레지스트리 단일 소스 — `[projects.<키>]` 블록으로 온보딩/오프보딩 |
| `src/loregist/config.py` | DB 접속·모델·`projects.toml` 로드·해석(`load_projects`) → `PROJECTS` dict 빌드, `infer_project()`, `get_db_connection()` |
| `src/loregist/chunking.py` | `hash_file/hash_chunk`, `split_md`(`##`/`###` 기준), `split_log`(빈 줄 기준). MIN 100 / MAX 1500자 merge·split |
| `src/loregist/embed.py` | 파일 스캔 → 원문 upsert → 청크 임베딩 → `doc_chunks` insert |
| `src/loregist/search.py` | 쿼리 임베딩 → cosine top-k (`WHERE project=` 스코프) |
| `src/loregist/tui.py` | TTY 출력 UX — 단계별 braille 스피너 + 색상 멀티라인 카드 + 번호 입력 기본앱 오픈. 비-TTY에선 전부 off |
| `src/loregist/rotate.py` | repo docs/dev/ → vault 이동 (라이프사이클 관리) |
| `loregist` | PATH 래퍼: `embed` / `search` / `projects` / `rotate` 서브커맨드 (`LOREGIST_CWD`로 호출 위치 전달) |
| `infra/docker-compose.yml` | pgvector 컨테이너 (port 5433, 타 DB와 포트 분리) |
| `infra/init.sql` | `doc_originals` / `doc_chunks` 스키마 + ivfflat·project 인덱스 |

## 스택

- **DB**: PostgreSQL 16 + pgvector, port **5433**, db/user `loregist`/`loregist`. 중앙 1 인스턴스를 모든 프로젝트가 `project` 컬럼으로 공유.
- **임베딩 모델**: `dragonkue/multilingual-e5-small-ko-v2` (384 dims, ~450MB, 한국어 특화 fine-tune). `models/`에 캐시 1벌.
- **Python**: 3.11 (`.python-version`), venv는 `.venv/`. `requirements.txt` / `requirements-dev.txt`.

## 명령어

```bash
loregist search "검색어"                    # 현재 프로젝트 시맨틱 검색 top-5 (default: hybrid mode)
loregist search "쿼리" --top-k 10 --min-score 0.85
loregist search "쿼리" --all-projects       # 크로스 프로젝트
loregist search "쿼리" --no-fallback        # 0건이어도 전체 재검색 안 함 (기본은 자동 fallback)
loregist search "쿼리" --json               # JSON 구조화 출력 (스크립팅용)
loregist search "쿼리" --plain              # TTY에서도 기존 한 줄 포맷 강제
loregist search "쿼리" --open 1             # 1번 결과를 즉시 기본 앱으로 열기 (루프 없음)
loregist search "쿼리" --no-interactive     # 색상 카드만 출력, 오픈 프롬프트 생략
loregist embed                              # 현재 프로젝트 전체 임베딩 (멱등)
loregist embed --dry-run                    # 대상 파일 목록만
loregist projects --json                    # 전체 프로젝트 목록 JSON
loregist projects --current                 # cwd 기준 현재 프로젝트 키
loregist rotate --dry-run                   # 7일 초과 날짜폴더 → vault 이동 대상 미리보기
loregist rotate --project project-a         # 실이동 (임베딩된 것만, vault 삭제 안 함)

make test-unit       # DB 불필요 단위 테스트
make test-int        # pgvector 기동 전제 통합 테스트
make test-all        # 전체 + 커버리지
make embed-dry       # project-a dry-run
make rotate-dry      # 현재 rotate 대상 미리보기
make db-up           # pgvector 컨테이너 기동
make db-down         # pgvector 컨테이너 중지

docker compose -f infra/docker-compose.yml up -d   # DB 기동
```

## 새 프로젝트 추가

1. `~/workspace/tools/personal-work/projects/{p}/` 디렉터리 생성 (`dev/`, `etc/` 하위)
2. `projects.toml`에 `[projects.{p}]` 블록 추가 (경로는 `~/workspace` 기준 상대경로, 없는 항목은 생략하면 `None`):
   - docs_root + vault + cold 타입 (project-a·project-b 형):
     ```toml
     [projects.{p}]
     docs_root = "tools/personal-work/projects/{p}/dev"
     vault     = "logvault/{p}"
     cold      = "logvault/{p}/cold"
     ```
   - vault + done 타입 (loregist·util 형, plans 폴더 rotate):
     ```toml
     [projects.{p}]
     vault = "logvault/{p}"
     done  = "loregist/{p}/plans/done"
     ```
3. `loregist embed --project {p}` 로 초기 임베딩

오프보딩: `projects.toml`에서 블록 삭제 + `loregist embed` (또는 `DELETE FROM doc_originals WHERE project='{p}'`)

## 규칙·주의

- **출력 UX (TTY 색상 카드/스피너/기본앱 오픈)**: TTY에서는 색상 멀티라인 카드·단계별 braille 스피너·번호 입력 오픈 프롬프트(루프)가 자동 활성화. 비-TTY(파이프·리다이렉트·pytest)에서는 기존 한 줄 `|` 포맷 유지. `--json` = 구조화 출력, `--plain` = TTY 강제 한 줄, `--open N` = N번 즉시 열기, `--no-interactive` = 프롬프트 생략. `NO_COLOR` 환경변수 존중, `LOREGIST_FORCE_COLOR`로 강제 가능.
- **e5 prefix 필수**: 임베딩 시 `passage: `, 쿼리 시 `query: ` 접두사를 붙인다(`embed_documents` / `embed_query`). 빼면 검색 품질 저하.
- **검색 모드**: 기본 `hybrid`(RRF 융합)가 vector·fts 단독보다 종합 우월(골든셋 80% vs 40%/60%). **약어·정확 키워드**는 vector 의미검색으로 안 잡히니 `hybrid`/`fts`를 쓴다. RRF `rrf_k`는 10~100에서 적중률 차이 없어 기본 60 유지(측정 근거: golden-queries.yaml + `loregist search --eval`).
- **검색 0건 fallback**: 현재 프로젝트 스코프가 0건이면 자동으로 `--all-projects` 재검색(stderr 안내 + `(전체, fallback)` 헤더). 빈 스코프(임베딩 0건 프로젝트)에서 특히 유용. `--no-fallback`으로 끈다.
- **멱등 임베딩**: `upsert_original`은 `ON CONFLICT (project, source_path)` UPDATE, `insert_chunks`는 해당 source의 청크를 DELETE 후 재삽입. 재실행해도 originals 수 불변.
- **원문 보존**: `doc_originals.full_text`에 전문 보관 → vault 삭제 후에도 복원 가능. DB가 1차 검색 계층.
- **임베딩 대상**: vault `*.log` + `cold/*.md`(rglob) + `done/*.md`(rglob) + `docs/dev/*/*.md`(날짜 폴더). **오늘 폴더·`_catalog`는 docs_root 스캔에서 제외**. (TODO: A 완료 시 catalog 임베딩 포함 방향으로 전환 예정 — plans/2026-06-19.컨텍스트관리_catalog_vault_후속계획.md A-3 참조)
- **라이프사이클**:
  - `docs_root/{YYYY-MM-DD}/` 폴더가 7일 초과 + 임베딩 완료 → `loregist rotate`로 `vault/{날짜}/` 이동(repo git rm). 매주 월 09:00 launchd 자동 실행(`scripts/rotate-all.sh`).
  - `plans/done/` 내 `YYYY-MM-DD*.md` 파일이 7일 초과 + 임베딩 완료 → `vault/cold/` 이동(repo git rm). 파일명 날짜 기준.
  - **`cold` 키 경로는 rotate 비대상** — 이미 cold storage 종착지. embed만 대상.
- **SSL 우회**: `src/loregist/config.py` 상단에서 httpx `verify=False` 패치(HuggingFace 다운로드용 SSL inspection 우회). 기업망 환경에서 `LOREGIST_NO_SSL_VERIFY=1`로 활성화. 모델 1회 워밍 후엔 로컬 캐시 사용.
- **rotate 경계조건**: `elapsed < ROTATE_TO_VAULT_DAYS` (`<=` 아님). 7일 이상이면 대상.
- **done_targets early return**: `if not targets and not done_targets:` — 두 조건 모두 비어야 early return. 하나만 체크하면 done rotate가 무시됨.

## 계획서 / 작업 이력은 여기에 두지 않는다

- **진행 중·미완료 계획**은 `plans/`에 있다. 후속 작업(FTS/hybrid, 자동 갱신, 라이프사이클, `_catalog`/OKF 차용 등)의 상세·착수 조건은 그쪽을 참조. CLAUDE.md에 복제하지 않는다(낡고, 자기 설계와 모순).
- **완료된 계획·수정보고서·트러블슈팅**은 `plans/done/`으로 저장한다. 임베딩 대상(`done.rglob("*.md")`)이므로 7일 후 vault 이동 후에도 `loregist search`로 검색 가능. 과거 결정·이력이 궁금하면 파일을 훑지 말고 먼저 검색할 것.
- **가이드성 문서** (라이프사이클 정리·설계 결정 등)는 `docs/`에 영구 보관하고 관련 내용을 CLAUDE.md에 반영한다. `docs/`는 임베딩·rotate 대상이 아님(CLAUDE.md가 단일 참조점). **공개 문서는 `docs/public/`에, 그 외 `docs/`는 내부 전용(publish·audit 차단)**.
- CLAUDE.md는 **안정 지침만** 담는다(아키텍처·명령어·규칙). 단발 상태값(임베딩 건수 등)은 DB에서 직접 확인.

## 설계 철학 (안정)

다량·고볼륨 원시 기록(로그·일일 작업문서) → loregist(검색 랭킹). 소수의 정제 지식(decision/topic) → OKF식 frontmatter catalog. 둘은 경쟁이 아니라 **파이프라인의 두 끝**이다.

## 롤백

`docker compose -f infra/docker-compose.yml down -v`. vault 원본과 `doc_originals.full_text`가 남아 있어 데이터 손실 없이 재구축 가능.

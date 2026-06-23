# loregist 사용 가이드

→ 도구 개요·원리는 [README.md](../../README.md), 아키텍처 상세는 [ARCHITECTURE.md](../../ARCHITECTURE.md)를 참조.

---

## Quick Start

> 처음 설치하는 경우 — 클론부터 프로젝트 등록까지 전체 절차는 [SETUP.md](SETUP.md)를 먼저 참조.

```bash
# 1. 환경변수 설정
cp .env.example .env
# LOREGIST_WORKSPACE: 문서·로그를 관리할 작업 루트 경로를 지정한다
# (예: ~/workspace, ~/projects 등 본인 환경에 맞게 수정)

# 2. 의존성 설치 + DB 기동
make setup

# 3. 임베딩 모델 사전 다운로드 (최초 1회, ~450MB, 1~3분 소요)
loregist warmup

# 4. 문서 임베딩
loregist embed

# 5. 검색
loregist search "찾을 내용"
```

---

## 명령어 요약

```bash
# 임베딩
loregist embed                          # 현재 프로젝트 전체 임베딩
loregist embed --dry-run                # 대상 파일 목록만 출력
loregist embed --incremental            # 변경된 파일만 임베딩

# 검색
loregist search "쿼리"                  # hybrid 모드 (기본)
loregist search "쿼리" --mode fts       # 키워드 검색
loregist search "쿼리" --all-projects   # 전체 프로젝트
loregist search "쿼리" --top-k 10
loregist search "쿼리" --json           # 구조화 출력 (스크립팅용)
loregist search "쿼리" --open 1         # 1번 결과 즉시 기본 앱으로 열기
loregist similar <파일경로>             # 지정 파일과 벡터 유사도 높은 과거 문서 검색 (전 프로젝트, top-k 기본 5)
loregist similar <파일경로> --top-k 10  # 유사 문서 상위 N개 반환

# 프로젝트
loregist project list                   # 등록 프로젝트 목록
loregist project current                # 현재 프로젝트 키

# 기록
loregist journal "메시지"               # 오늘 날짜 로그 파일에 타임스탬프 기록
loregist watch                          # 현재 프로젝트 vault 감시 (파일 변경 시 자동 embed)
loregist watch --dir ~/notes            # 특정 디렉터리 감시

# 라이프사이클
loregist rotate --dry-run               # 이동 대상 미리보기
loregist rotate                         # vault 이동 실행
# ⚠️  vault-cleanup: 파괴적 opt-in — projects.toml에 vault_cleanup 키 설정 필수, 삭제는 비가역(파일 unlink)
loregist vault-cleanup --project <키> --dry-run   # 정리 대상 미리보기 (기본값, 실제 삭제 없음)
loregist vault-cleanup --project <키> --apply     # 실제 삭제 실행 (--apply 명시 필수, DB full_text는 보존)

# catalog
loregist catalog-init --project {p}     # _wiki/ 초기화 (최초 1회)
loregist catalog --project {p}          # TOPICS.md·DECISIONS.md 자동 갱신

# 개발/운영
loregist status                         # 프로젝트별 임베딩 청크 수·최종 임베딩 시각·vault 경로 대시보드 출력 (DB 연결 진단 겸용)
make test-unit      # 단위 테스트 (DB 불필요)
make test-int       # 통합 테스트 (pgvector 필요)
make db-up          # pgvector 컨테이너 기동
make db-down        # pgvector 컨테이너 중지
```

---

## 비개발자 사용 가이드

터미널에 익숙하지 않아도 `journal`과 `watch` 명령으로 기록·자동화를 시작할 수 있다.

### 빠른 시작

```bash
# 1. 설치 (최초 1회, loregist 바이너리를 PATH에 등록)
make install

# 2. 오늘 기록 남기기
loregist journal "API 스펙 검토 완료, v2 엔드포인트 유지 결정"
# → <vault>/journal/YYYY-MM-DD.log 에 [HH:MM] 메시지 자동 저장

# 3. 디렉터리 감시 (파일 저장 시 자동 embed)
loregist watch                        # 현재 프로젝트 vault 감시
loregist watch --dir ~/notes          # 특정 디렉터리 감시
# → Ctrl-C 로 종료
```

### macOS 자동화 (터미널 없이 사용)

#### Shortcuts 앱 단축키 (텍스트 입력 → 자동 기록)

1. [`scripts/examples/loregist-journal.shortcut`](../../scripts/examples/loregist-journal.shortcut)을 더블클릭해 Shortcuts 앱으로 가져오기
2. Shortcuts 앱에서 단축키 지정 (예: ⌥Space)
3. 이후 어디서든 단축키 → 텍스트 입력창 → 자동 로그 기록

#### launchd 자동 embed (1시간마다)

```bash
# 설치
cp scripts/examples/auto-embed.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/io.loregist.auto-embed.plist

# 제거
launchctl unload ~/Library/LaunchAgents/io.loregist.auto-embed.plist
rm ~/Library/LaunchAgents/io.loregist.auto-embed.plist
```

자세한 내용: [`scripts/examples/auto-embed.plist`](../../scripts/examples/auto-embed.plist)

---

## 외부 활동 소스 연동

[`scripts/examples/`](../../scripts/examples/) 디렉터리에 활동 소스 → 로그 파일 변환 예시 스크립트가 있다.

| 스크립트 | 설명 | 의존 |
|----------|------|------|
| [`github-digest.sh`](../../scripts/examples/github-digest.sh) | 오늘 GitHub 알림을 로그 파일에 append | `gh` CLI, `jq` |
| [`jira-digest.sh`](../../scripts/examples/jira-digest.sh) | 오늘 Jira 업데이트 이슈를 로그 파일에 append | `curl`, `jq`, `JIRA_URL`, `JIRA_TOKEN` |

```bash
# GitHub 활동 기록 (gh CLI 인증 필요)
./scripts/examples/github-digest.sh

# Jira 활동 기록
JIRA_URL=https://yourorg.atlassian.net JIRA_TOKEN=<token> ./scripts/examples/jira-digest.sh
```

---

## 새 프로젝트 추가

1. 프로젝트 문서 디렉터리를 생성한다 (`dev/`, `etc/` 하위).

2. `projects.toml`에 블록 추가 — 경로는 `LOREGIST_WORKSPACE` 기준 상대경로:

   ```toml
   # 일반 프로젝트: 작업문서(docs_root) + 로그(vault) + 콜드 스토리지(cold)
   [projects.myproject]
   docs_root     = "path/to/myproject/dev"
   vault         = "logvault/myproject"
   cold          = "logvault/myproject/cold"
   catalog       = true   # _wiki/ 인덱스 사용 시
   extensions    = ["md", "log", "txt"]   # 임베딩·watch·vault-cleanup 대상 확장자 (기본값: ["md","log","txt"], dot 없이 작성)
   vault_cleanup = true   # cold+vault 오래된 파일 삭제 opt-in (기본 90일 보존, 미설정 시 삭제 안 함)
   # vault_cleanup = 30   # 일수 직접 지정 가능
   # hot_days = 3         # rotate 기준일 override (기본 7일, 미설정 시 전역값 사용)

   # plans/done 로테이션만 필요한 경우
   [projects.myproject]
   vault = "logvault/myproject"
   done  = "path/to/myproject/plans/done"

   # handbook: 감시·참조할 위키 파일·디렉터리 목록 (wiki_sources는 deprecated, handbook 사용 권장)
   # 문자열 단축형(path만)과 inline table({path, writable, update_when}) 혼용 가능
   [projects.myproject]
   docs_root = "path/to/myproject/dev"
   vault     = "logvault/myproject"
   handbook  = [
     "path/to/ref-doc.md",                                        # 문자열 단축형 (path만, writable=false)
     {path = "path/to/auto-updated.md", writable = true},         # 쓰기 허용
     {path = "path/to/trigger.md", writable = true, update_when = "명령어 추가·변경 시"},  # 업데이트 트리거 조건 명시
   ]
   # handbook 스키마:
   #   path        (필수): 파일·디렉터리 경로. WORKSPACE 상대 또는 절대경로, glob 가능.
   #   writable    (선택, 기본 false): 자동 업데이트(쓰기) 허용 여부.
   #   update_when (선택, 기본 null): 업데이트 트리거 조건 문자열.
   #
   # catalog 암묵 활성화:
   #   catalog 키 미설정 + wiki 1건 이상 + docs_root 존재 → {docs_root}/_wiki 자동 설정
   #   catalog 경로를 커스텀하려면 catalog = "경로" 명시
   ```

3. 초기 임베딩:

   ```bash
   loregist embed --project myproject
   ```

오프보딩: `projects.toml`에서 블록 삭제 후 `loregist embed` (또는 `DELETE FROM doc_originals WHERE project='myproject'`).

---

## 라이프사이클

### rotate — Hot → Cold 이동

`loregist rotate`는 hot 파일 중 일정 기간이 지난 것을 vault(cold)로 이동한다.

```bash
loregist rotate --dry-run   # 이동 대상 미리보기
loregist rotate             # 실행
```

> **HOT 기간 변경**: 기준일은 기본 7일(`ROTATE_TO_VAULT_DAYS`)이며, `projects.toml` 프로젝트 블록에 `hot_days = <int>`를 선언하면 해당 프로젝트에만 적용된다. 미선언 시 7일 기본값 유지.

### vault_cleanup — Cold 파일 삭제

rotate로 이동된 파일을 일정 기간 후 삭제한다. **opt-in 전용** — `projects.toml`에 `vault_cleanup` 키를 추가한 프로젝트만 동작한다.

```toml
vault_cleanup = true    # 기본 90일 보존 후 삭제
vault_cleanup = 30      # 일수 직접 지정
```

```bash
loregist vault-cleanup --project <키> --dry-run   # 삭제 후보 미리보기
loregist vault-cleanup --project <키> --apply     # 실제 삭제 (비가역)
```

DB의 `doc_originals.full_text`(원문)은 삭제 후에도 보존되므로 원문 복원이 가능하다.

---

## catalog 기능

프로젝트의 도메인 개념(topic)·의사결정(decision)을 `_wiki/` 인덱스로 관리하는 기능이다.

1. `projects.toml`에 `catalog = true` 추가 (위 프로젝트 추가 예시 참조)

2. `_wiki/` 초기화 (최초 1회):

   ```bash
   loregist catalog-init --project {p}
   ```

   → `{docs_root}/_wiki/TOPICS.md`·`DECISIONS.md`가 AUTO 마커 포함 템플릿으로 생성된다.

3. 이후 갱신 (또는 post-commit 훅):

   ```bash
   loregist catalog --project {p}
   ```

재실행 시 기존 파일을 덮어쓰지 않는다(멱등). 재생성하려면 `--force`:

```bash
loregist catalog-init --project {p} --force
```

`_wiki/` 내 T/D 파일 간 edges 무결성(dangling·asymmetric·self-ref·orphan)을 점검하려면 `--lint`:

```bash
loregist catalog --project {p} --lint          # 무결성 점검 결과 출력
loregist catalog --project {p} --lint --json   # JSON 형식으로 출력 (스크립팅용)
```

---

## DB 연결 정보

pgAdmin 등 외부 도구로 직접 접속할 때:

| 항목 | 값 |
|------|----|
| Host | `localhost` |
| Port | `5433` |
| Database | `loregist` |
| Username | `loregist` |
| Password | `vector_local` (기본값, `.env`로 변경 가능) |

주요 테이블: `doc_originals`(원문), `doc_chunks`(임베딩 청크)

---

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LOREGIST_DB_PASSWORD` | `vector_local` | PostgreSQL 비밀번호 |
| `LOREGIST_WORKSPACE` | `~/workspace` | 작업 루트 경로 |
| `LOREGIST_NO_SSL_VERIFY` | `1` | 기업망 SSL inspection 우회 (1=활성) |

---

## 로그 형식 가이드

최소 권장 형식과 청킹 규칙은 [log-format.md](log-format.md)를 참조.

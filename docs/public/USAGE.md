# stashdex 사용 가이드

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
stashdex warmup

# 4. 문서 임베딩
stashdex embed

# 5. 검색
stashdex search "찾을 내용"
```

---

## 간편 사용 가이드

터미널에 익숙하지 않아도 `journal`과 `watch` 명령으로 기록·자동화를 시작할 수 있다.

### 빠른 시작

```bash
# 1. 설치 (최초 1회, stashdex 바이너리를 PATH에 등록)
make install

# 2. 오늘 기록 남기기
stashdex journal "API 스펙 검토 완료, v2 엔드포인트 유지 결정"
# → <vault>/journal/YYYY-MM-DD.log 에 [HH:MM] 메시지 자동 저장

# 3. 디렉터리 감시 (파일 저장 시 자동 embed)
stashdex watch                        # 현재 프로젝트 vault 감시
stashdex watch --dir ~/notes          # 특정 디렉터리 감시
# → Ctrl-C 로 종료
```

### 간편 기록 키트 (일괄 설치)

터미널 없이 macOS에서 stashdex를 쓰기 위한 3부품 묶음이다. 개발자가 `install-nondev-kit.sh`를 한 번 실행하면 아래 부품이 자동으로 배치·등록된다.

```bash
# 간편 키트 일괄 설치 (변수 치환·배치·launchd 등록 포함)
bash scripts/install-nondev-kit.sh
```

설치 후 입력 동선은 3단계로 끝난다:

1. **더블클릭** — `stashdex-journal.command`를 Finder에서 더블클릭한다 (Shortcuts 앱 단축키를 등록하면 키보드 단축키 한 번으로 대체 가능)
2. **타이핑** — 대화창에 기록할 내용을 입력한다
3. **끝** — Enter를 누르면 기록이 저장된다. 터미널·명령어 불필요

| 부품 | 역할 | 최종 배치 위치 |
|------|------|----------------|
| `stashdex-journal.shortcut` | Shortcuts 앱 단축키 — 키보드 단축키 한 번으로 텍스트 입력창을 열어 stashdex journal 기록 | Shortcuts 앱 (더블클릭으로 가져오기) |
| `stashdex-journal.command` | 더블클릭 입력 진입점 — Finder에서 더블클릭하면 대화창이 열리고 텍스트를 입력해 기록 | `~/Applications/` 또는 바탕화면 |
| `auto-embed.plist` | 1시간 주기 자동 embed LaunchAgent — launchd가 매 1시간마다 `stashdex embed`를 자동 실행 | `~/Library/LaunchAgents/io.stashdex.auto-embed.plist` |

개발자 세팅 전체 절차는 [SETUP.md](SETUP.md)를 참조.

#### 한계 (솔직하게)

- **개발자 1회 세팅 필요** — `scripts/install-nondev-kit.sh`를 개발자가 먼저 실행해야 키트가 배치된다. 본인이 직접 실행하기 어렵다면 개발자에게 요청한다.
- **macOS 전용** — `.command`, LaunchAgent(`plist`)는 macOS에서만 동작한다. Windows·Linux에서는 이 키트를 사용할 수 없다.
- **embed 엔진(Docker) 상시 가동 전제** — 검색 색인은 Docker 기반 pgvector에 저장된다. Docker가 꺼져 있으면 `auto-embed`가 실패해 새로 기록한 내용이 검색 색인에 반영되지 않는다. 기록 자체는 남지만, 나중에 검색으로 찾으려면 Docker가 켜진 상태에서 `stashdex embed`를 수동 실행해야 한다.

아래는 각 부품의 개별 설치·동작 방법이다.

### macOS 자동화 (터미널 없이 사용)

#### Shortcuts 앱 단축키 (텍스트 입력 → 자동 기록)

1. [`scripts/examples/stashdex-journal.shortcut`](../../scripts/examples/stashdex-journal.shortcut)을 더블클릭해 Shortcuts 앱으로 가져오기
2. Shortcuts 앱에서 단축키 지정 (예: ⌥Space)
3. 이후 어디서든 단축키 → 텍스트 입력창 → 자동 로그 기록

#### stashdex-journal.command (더블클릭 진입점)

Shortcuts 앱 대신 Finder에서 더블클릭으로 기록창을 열고 싶을 때 사용한다.

```bash
# ~/Applications/ 에 복사하면 더블클릭으로 실행 가능
cp scripts/examples/stashdex-journal.command ~/Applications/
```

#### launchd 자동 embed (1시간마다)

```bash
# 설치
cp scripts/examples/auto-embed.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/io.stashdex.auto-embed.plist

# 제거
launchctl unload ~/Library/LaunchAgents/io.stashdex.auto-embed.plist
rm ~/Library/LaunchAgents/io.stashdex.auto-embed.plist
```

자세한 내용: [`scripts/examples/auto-embed.plist`](../../scripts/examples/auto-embed.plist)

---

## 명령어 요약

→ 전체 명령어: [COMMANDS.md](COMMANDS.md)

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

   → 상세 설정: [PROJECTS.md](PROJECTS.md)

3. 초기 임베딩:

   ```bash
   stashdex embed --project myproject
   ```

오프보딩: `projects.toml`에서 블록 삭제 후 `stashdex embed` (또는 `DELETE FROM doc_originals WHERE project='myproject'`).

---

## 라이프사이클

### rotate — Hot → Cold 이동

`stashdex rotate`는 hot 파일 중 일정 기간이 지난 것을 vault(cold)로 이동한다.

```bash
stashdex rotate --dry-run                # 이동 대상 미리보기
stashdex rotate                          # 실행
stashdex rotate --extensions md,log,txt  # 확장자 런타임 override
```

> **HOT 기간 변경**: 기준일은 기본 7일(`ROTATE_TO_VAULT_DAYS`)이며, `projects.toml` 프로젝트 블록에 `hot_days = <int>`를 선언하면 해당 프로젝트에만 적용된다. 미선언 시 7일 기본값 유지.

> **대상 확장자**: rotate는 `projects.toml`의 `extensions`(기본 `["md", "log", "txt"]`)를 동일하게 적용한다. `--extensions md,log,txt` CLI 옵션으로 런타임 override 가능. 우선순위: CLI > projects.toml extensions > 기본값.

### vault_cleanup — Cold 파일 삭제

rotate로 이동된 파일을 일정 기간 후 삭제한다. **opt-in 전용** — `projects.toml`에 `vault_cleanup` 키를 추가한 프로젝트만 동작한다.

```toml
vault_cleanup = true    # 기본 90일 보존 후 삭제
vault_cleanup = 30      # 일수 직접 지정
```

```bash
stashdex vault-cleanup --project <키> --dry-run   # 삭제 후보 미리보기
stashdex vault-cleanup --project <키> --apply     # 실제 삭제 (비가역)
```

DB의 `doc_originals.full_text`(원문)은 삭제 후에도 보존되므로 원문 복원이 가능하다.

---

## catalog 기능

프로젝트의 도메인 개념(topic)·의사결정(decision)을 `_wiki/` 인덱스로 관리하는 기능이다.

1. `projects.toml`에 `catalog = true` 추가 ([PROJECTS.md](PROJECTS.md))

2. `_wiki/` 초기화 (최초 1회):

   ```bash
   stashdex catalog-init --project {p}
   ```

   → `{docs_root}/_wiki/TOPICS.md`·`DECISIONS.md`가 AUTO 마커 포함 템플릿으로 생성된다.

3. 이후 갱신 (또는 post-commit 훅):

   ```bash
   stashdex catalog --project {p}
   ```

재실행 시 기존 파일을 덮어쓰지 않는다(멱등). 재생성하려면 `--force`:

```bash
stashdex catalog-init --project {p} --force
```

`_wiki/` 내 T/D 파일 간 edges 무결성(dangling·asymmetric·self-ref·orphan)을 점검하려면 `--lint`:

```bash
stashdex catalog --project {p} --lint          # 무결성 점검 결과 출력
stashdex catalog --project {p} --lint --json   # JSON 형식으로 출력 (스크립팅용)
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

### LOREGIST_WORKSPACE 설정 방법

**방법 1 — 셸 프로파일 (`.zshrc` / `.bash_profile`)**

```bash
export LOREGIST_WORKSPACE=/절대/경로/workspace
```

`~/.zshrc`(또는 `~/.bash_profile`)에 위 줄을 추가하고 `source ~/.zshrc`로 즉시 반영한다. 터미널을 새로 열어도 영구 적용된다.

**방법 2 — Claude Code 세션 전용 (`.claude/settings.json`)**

Claude Code 세션에서만 환경변수를 주입하려면 프로젝트 루트의 `.claude/settings.json`에 `env` 블록을 추가한다.

```json
{
  "env": {
    "LOREGIST_WORKSPACE": "/절대/경로/workspace"
  }
}
```

> 두 방법을 동시에 설정하면 `.zshrc` 값이 우선 적용된다.
> Claude Code 비(非)세션 환경(터미널 직접 실행 등)에서는 `.zshrc` 값이 사용된다.

---

## Claude Code 통합 설정

Claude Code에서 자연어로 "어제 결정 검색해서 정리해줘"라고 말하면 Claude가 자동으로 `stashdex search`를 호출한다. 이 동선(B2 모델)을 켜려면 **각 프로젝트의 `CLAUDE.md`에 아래 규칙 블록을 추가**한다. 이것이 B2(자연어 위임)의 on/off 스위치다.

```
## 문서·로그 컨텍스트

- 과거 이력 검색: `stashdex search "검색어" --project <프로젝트명>`
- 직접 읽지 말 것: `*.log`, `cold/**`
```

이 블록을 추가하면 Claude가 관련 기록을 검색해 컨텍스트로 참고한다. `<프로젝트명>`은 `projects.toml`에 등록한 프로젝트 키다.

> `LOREGIST_WORKSPACE` 환경변수 설정은 [환경변수 절](#환경변수)을 참조.

**Claude가 검색을 소비하는 흐름**: Claude가 `stashdex search "쿼리" --json`으로 관련 청크를 JSON으로 수신해 컨텍스트에 주입한다. 기록 전체를 읽는 대신 추려진 관련 기록만 참고하므로 토큰을 아낀다. 사람이 직접 TUI로 검색하는 것과 달리, 자연어 위임(B2) 동선에서는 Claude가 이 명령을 자동으로 호출한다.

---

## 로그 형식 가이드

최소 권장 형식과 청킹 규칙은 [log-format.md](log-format.md)를 참조.

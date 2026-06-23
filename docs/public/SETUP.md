# loregist 설치 가이드

→ 도구 개요·원리는 [README.md](../../README.md), 사용법은 [USAGE.md](USAGE.md), 아키텍처 상세는 [ARCHITECTURE.md](../../ARCHITECTURE.md)를 참조.

---

## Prerequisites

- Python 3.11
- Docker (pgvector 컨테이너)
- `make`

---

## 설치 절차

### 1. 저장소 클론

```bash
git clone <repo-url> loregist
cd loregist
```

---

### 2. 보안 훅 활성화 (클론 후 1회)

이 repo는 민감 정보 유출을 차단하는 pre-commit 훅을 포함한다.  
**클론한 뒤 반드시 아래 명령을 1회 실행해 훅을 활성화한다.**

```bash
git config core.hooksPath .githooks
```

검사 로직은 `scripts/audit.sh`에 집중되어 있으며, pre-commit 훅·CI가 공용한다.

```bash
# 수동 검사 (staged 기준)
scripts/audit.sh --staged

# 수동 검사 (전체 추적 파일 기준, CI용)
scripts/audit.sh --tree
```

---

### 3. PATH 등록 (`make install`)

`loregist` 바이너리를 `/usr/local/bin`에 심링크해 어디서든 호출할 수 있도록 등록한다.

```bash
make install
```

> 개발자가 아닌 경우에도 이 단계가 필요하다. `loregist` 명령을 터미널 어디서나 실행하려면 PATH 등록이 전제되어야 한다.

---

### 4. 가상환경 및 의존성 설치 (`make setup`)

Python 가상환경(`.venv/`)을 생성하고 패키지 의존성을 설치한다.

```bash
make setup
```

---

### 5. DB 기동 (`make db-up`)

pgvector 컨테이너를 기동한다. 임베딩 색인과 검색 기능에 필요하다.

```bash
make db-up
```

> 컨테이너가 정상 기동됐는지 확인하려면 `loregist status`를 실행한다.

---

### 6. 임베딩 모델 준비 (`loregist warmup`)

최초 1회 임베딩 모델을 다운로드·캐싱한다. 약 450MB, 1~3분 소요된다.

```bash
loregist warmup
```

---

### 7. 프로젝트 등록 (`loregist project add <key>`)

기록·검색할 프로젝트를 등록한다. 대화형으로 프로젝트 키·경로를 입력받아 `projects.toml`에 자동 등록된다.

```bash
loregist project add <key>
```

등록된 프로젝트 목록 확인:

```bash
loregist project list
```

---

### 8. 비개발자 키트 설치 (`scripts/install-nondev-kit.sh`)

코드·인프라 작업 없이 loregist를 일상 업무에 활용할 수 있도록 macOS 자동화 도구(Shortcuts 앱 단축키, launchd 자동 embed 등)를 설치한다.

```bash
bash scripts/install-nondev-kit.sh
```

설치 내용 및 이후 사용법은 아래 [비개발자 키트 이후 단계](#비개발자-키트-이후-단계)를 참조.

---

## 설치 완료 확인

```bash
# DB 연결 및 프로젝트 상태 확인
loregist status

# 첫 번째 기록 남기기
loregist journal "loregist 설치 완료"

# 검색 테스트
loregist search "설치 완료"
```

---

## 비개발자 키트 이후 단계

`scripts/install-nondev-kit.sh` 실행 후 아래 기능을 바로 사용할 수 있다.

### Shortcuts 앱 단축키 (텍스트 입력 → 자동 기록)

1. [`scripts/examples/loregist-journal.shortcut`](../../scripts/examples/loregist-journal.shortcut)을 더블클릭해 Shortcuts 앱으로 가져오기
2. Shortcuts 앱에서 단축키 지정 (예: ⌥Space)
3. 이후 어디서든 단축키 → 텍스트 입력창 → 자동 로그 기록

### launchd 자동 embed (1시간마다)

설치 스크립트가 `~/Library/LaunchAgents/`에 plist를 등록한다. 이후 1시간마다 자동으로 `loregist embed`가 실행된다.

수동 제거가 필요하면:

```bash
launchctl unload ~/Library/LaunchAgents/io.loregist.auto-embed.plist
rm ~/Library/LaunchAgents/io.loregist.auto-embed.plist
```

### 일상 기록 루프

```bash
# 오늘 기록 남기기
loregist journal "오늘 한 일 메모"

# 디렉터리 감시 (파일 저장 시 자동 embed)
loregist watch

# 과거 이력 검색
loregist search "찾을 내용"
```

---

## 롤백

```bash
docker compose -f infra/docker-compose.yml down -v
```

vault 원본과 `doc_originals.full_text`가 남아 있어 데이터 손실 없이 재구축 가능하다.

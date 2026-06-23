# loregist 사용 가이드

→ 전체 사용 가이드는 [docs/public/USAGE.md](docs/public/USAGE.md) 참조.

---

## 비개발자 기록 키트

터미널 없이 macOS에서 loregist를 사용하기 위한 3부품 구성이다.
`install-nondev-kit.sh`를 실행하면 아래 부품이 자동으로 배치·등록된다.

### 비개발자 입력 동선 (3단계)

1. **더블클릭** — `loregist-journal.command`를 Finder에서 더블클릭한다
2. **타이핑** — 대화창에 기록할 내용을 입력한다
3. **끝** — Enter를 누르면 기록이 저장된다. 터미널·명령어 불필요

> Shortcuts 앱 단축키(`loregist-journal.shortcut`)를 등록하면 단계 1을 키보드 단축키 한 번으로 대체할 수 있다.

### 한계 (솔직하게)

- **개발자 1회 세팅 필요** — `scripts/install-nondev-kit.sh`를 개발자가 먼저 실행해야 키트가 배치된다. 비개발자 본인이 직접 실행하기 어렵다면 개발자에게 요청한다.
- **macOS 전용** — `.command`, LaunchAgent(`plist`)는 macOS에서만 동작한다. Windows·Linux에서는 이 키트를 사용할 수 없다.
- **embed 엔진(Docker) 상시 가동 전제** — 검색 색인은 Docker 기반 pgvector에 저장된다. Docker가 꺼져 있으면 `auto-embed`가 실패해 새로 기록한 내용이 검색 색인에 반영되지 않는다. 기록 자체는 남지만, 나중에 검색으로 찾으려면 Docker가 켜진 상태에서 `loregist embed`를 수동 실행해야 한다.

### 키트 구성

| 부품 | 역할 | 최종 배치 위치 |
|------|------|----------------|
| `loregist-journal.shortcut` | Shortcuts 앱 단축키 — 키보드 단축키 한 번으로 텍스트 입력창을 열어 loregist journal 기록 | Shortcuts 앱 (더블클릭으로 가져오기) |
| `loregist-journal.command` | 더블클릭 입력 진입점 — Finder에서 더블클릭하면 대화창이 열리고 텍스트를 입력해 기록 | `~/Applications/` 또는 바탕화면 |
| `auto-embed.plist` | 1시간 주기 자동 embed LaunchAgent — launchd가 매 1시간마다 `loregist embed`를 자동 실행 | `~/Library/LaunchAgents/io.loregist.auto-embed.plist` |

개발자 세팅 전체 절차는 [docs/public/SETUP.md](docs/public/SETUP.md)를 참조.

### 설치

```bash
# 비개발자 키트 일괄 설치 (변수 치환·배치·launchd 등록 포함)
bash scripts/install-nondev-kit.sh
```

### 수동 설치 (개별 부품)

```bash
# loregist-journal.command: ~/Applications/ 에 복사 후 더블클릭 가능
cp scripts/examples/loregist-journal.command ~/Applications/

# auto-embed.plist: LaunchAgents에 복사 후 launchd 등록
cp scripts/examples/auto-embed.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/io.loregist.auto-embed.plist
```

`loregist-journal.shortcut`는 `scripts/examples/` 에서 더블클릭하면
Shortcuts 앱으로 자동 가져온다. 가져온 후 Shortcuts 앱에서 단축키를 지정한다.

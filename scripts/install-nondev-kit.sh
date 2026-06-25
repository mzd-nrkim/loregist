#!/usr/bin/env bash
# install-nondev-kit.sh — stashdex 비개발자 키트 설치 스크립트
# 사용법: bash scripts/install-nondev-kit.sh
# 멱등(idempotent): 이미 설치된 항목은 스킵하거나 reload만 수행한다.
set -euo pipefail

# ── 기본 변수 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_KEY="personal-work"

LOREGIST_SYMLINK="/usr/local/bin/stashdex"
LAUNCH_AGENT_LABEL="io.stashdex.auto-embed"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_SRC="$REPO_DIR/scripts/examples/auto-embed.plist"
PLIST_DST="$LAUNCH_AGENT_DIR/${LAUNCH_AGENT_LABEL}.plist"
COMMAND_SRC="$REPO_DIR/scripts/examples/stashdex-journal.command"
SHORTCUT_SRC="$REPO_DIR/scripts/examples/stashdex-journal.shortcut"
APPS_DIR="$HOME/Applications"
COMMAND_DST="$APPS_DIR/stashdex-journal.command"

# ── 출력 헬퍼 ─────────────────────────────────────────────────────────────────
info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*" >&2; }
skip()  { echo "[SKIP]  $*"; }
done_() { echo "[DONE]  $*"; }

# ── C-0: Python 가상환경 셋업 ─────────────────────────────────────────────────
setup_venv() {
  info "C-0: Python 가상환경 셋업 중..."
  if [[ -d "$REPO_DIR/.venv" ]]; then
    skip ".venv 이미 존재 ($REPO_DIR/.venv)"
    return 0
  fi
  info "  .venv 없음 — make setup 실행 중..."
  make -C "$REPO_DIR" setup
  done_ "make setup 완료"
}

# ── C-1: DB(Docker) 기동 ─────────────────────────────────────────────────────
ensure_db_up() {
  info "C-1: stashdex DB(Docker 컨테이너) 기동 확인 중..."
  if docker ps --filter name=loregist 2>/dev/null | grep -q loregist; then
    skip "stashdex Docker 컨테이너 이미 가동 중."
    return 0
  fi
  info "  컨테이너 미기동 — make db-up 실행 중..."
  make -C "$REPO_DIR" db-up
  done_ "stashdex DB 기동 완료"
}

# ── C-1b: 임베딩 모델 웜업 ───────────────────────────────────────────────────
warmup_model() {
  info "C-1b: 임베딩 모델 캐시 확인 중..."
  # 캐시 경로: <repo>/models/models--dragonkue--multilingual-e5-small-ko-v2
  # (src/loregist/embed.py: MODELS_DIR / ("models--" + MODEL_NAME.replace("/", "--")))
  local model_cache="$REPO_DIR/models/models--dragonkue--multilingual-e5-small-ko-v2"
  if [[ -d "$model_cache" ]]; then
    skip "임베딩 모델 캐시 이미 존재 ($model_cache)"
    return 0
  fi
  info "  모델 캐시 없음 — stashdex warmup 실행 중 (시간 소요)..."
  stashdex warmup
  done_ "임베딩 모델 웜업 완료"
}

# ── C-1c: stashdex 프로젝트 등록 ─────────────────────────────────────────────
ensure_project() {
  info "C-1c: stashdex 프로젝트 등록 확인 중..."
  if stashdex project list 2>/dev/null | grep -q "$PROJECT_KEY"; then
    done_ "프로젝트 '$PROJECT_KEY' 이미 등록됨."
    return 0
  fi
  info "  프로젝트 '$PROJECT_KEY' 미등록 — stashdex project add 실행..."
  info "  (대화형 입력이 시작됩니다. 프롬프트에 따라 입력하세요)"
  stashdex project add
  done_ "프로젝트 등록 완료"
}

# ── C-6(구): embed 엔진 상태 점검 (ensure_db_up으로 대체됨) ─────────────────
# check_embed_engine 함수는 ensure_db_up으로 격상되어 제거되었습니다.

# ── C-2: stashdex 바이너리 PATH 등록 / 심링크 ────────────────────────────────
install_loregist_symlink() {
  info "C-2: stashdex 심링크 설정 중... (대상: $LOREGIST_SYMLINK)"

  # 실제 바이너리 위치 자동 탐색 — 우선순위: 레포 루트 래퍼 > .venv/bin > homebrew
  local bin_target=""

  # 1) 레포 루트의 래퍼 스크립트
  if [[ -f "$REPO_DIR/stashdex" && -x "$REPO_DIR/stashdex" ]]; then
    bin_target="$REPO_DIR/stashdex"
  fi

  # 2) .venv/bin/stashdex (레포 기준)
  if [[ -z "$bin_target" ]]; then
    bin_target="$(find "$REPO_DIR/.venv/bin" -name "stashdex" 2>/dev/null | head -1)"
  fi

  # 3) 상위 레포(stashdex) .venv/bin/stashdex
  if [[ -z "$bin_target" ]]; then
    bin_target="$(find "$REPO_DIR/../stashdex/.venv/bin" -name "stashdex" 2>/dev/null | head -1)"
  fi

  if [[ -z "$bin_target" ]]; then
    warn "stashdex 바이너리를 찾을 수 없습니다. 수동으로 설치 후 재실행하거나 심링크를 직접 생성하세요."
    warn "  예: sudo ln -sf /path/to/stashdex $LOREGIST_SYMLINK"
    return 0
  fi

  info "  탐색된 바이너리: $bin_target"

  # 이미 동일 심링크가 존재하면 스킵
  if [[ -L "$LOREGIST_SYMLINK" && "$(readlink "$LOREGIST_SYMLINK")" == "$bin_target" ]]; then
    skip "심링크 이미 존재 ($LOREGIST_SYMLINK -> $bin_target)"
    return 0
  fi

  # 다른 대상 또는 일반 파일이면 교체
  if [[ -e "$LOREGIST_SYMLINK" || -L "$LOREGIST_SYMLINK" ]]; then
    info "  기존 항목 제거 후 재생성..."
    sudo rm -f "$LOREGIST_SYMLINK" 2>/dev/null || true
  fi

  if sudo ln -sf "$bin_target" "$LOREGIST_SYMLINK" 2>/dev/null; then
    done_ "심링크 생성: $LOREGIST_SYMLINK -> $bin_target"
  else
    warn "심링크 생성 실패 (sudo 권한 없음). 개발자가 수동으로 실행하세요:"
    warn "  sudo ln -sf $bin_target $LOREGIST_SYMLINK"
  fi
}

# ── C-3: auto-embed LaunchAgent 등록 ─────────────────────────────────────────
install_launch_agent() {
  info "C-3: LaunchAgent 설치 중... ($LAUNCH_AGENT_LABEL)"

  if [[ ! -f "$PLIST_SRC" ]]; then
    warn "plist 원본 없음: $PLIST_SRC — LaunchAgent 설치 스킵"
    return 0
  fi

  # LaunchAgents 디렉터리 생성
  mkdir -p "$LAUNCH_AGENT_DIR"

  # plist 복사 (ProgramArguments에 /usr/local/bin/stashdex가 이미 고정되어 있음)
  # 현재 plist는 `stashdex embed`만 있으므로 --project 없이 전체 embed 동작 유지
  cp "$PLIST_SRC" "$PLIST_DST"
  done_ "plist 복사: $PLIST_DST"

  # 멱등 reload: 이미 load된 경우 unload 후 reload
  if launchctl list 2>/dev/null | grep -q "$LAUNCH_AGENT_LABEL"; then
    info "  기존 LaunchAgent 언로드 후 재로드..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
  fi

  launchctl load "$PLIST_DST"
  done_ "LaunchAgent 로드 완료: $LAUNCH_AGENT_LABEL"
}

# ── C-4: .command 배치 ───────────────────────────────────────────────────────
install_command() {
  info "C-4: stashdex-journal.command 배치 중..."

  if [[ ! -f "$COMMAND_SRC" ]]; then
    warn ".command 원본 없음: $COMMAND_SRC — 스킵"
    return 0
  fi

  # ~/Applications 디렉터리 생성
  mkdir -p "$APPS_DIR"

  # 원본을 임시 파일로 복사 후 PROJECT_KEY sed 치환, 그 뒤 배치
  local tmp_cmd
  tmp_cmd="$(mktemp /tmp/stashdex-journal-XXXXXX.command)"

  sed "s|PROJECT_KEY=\".*\"|PROJECT_KEY=\"$PROJECT_KEY\"|g" "$COMMAND_SRC" > "$tmp_cmd"
  chmod +x "$tmp_cmd"
  mv "$tmp_cmd" "$COMMAND_DST"
  chmod +x "$COMMAND_DST"

  done_ ".command 배치 완료: $COMMAND_DST (PROJECT_KEY=$PROJECT_KEY)"
}

# ── C-5: Shortcut 수동 임포트 안내 ───────────────────────────────────────────
guide_shortcut_import() {
  info "C-5: Shortcut 자동 임포트는 불가능합니다. 아래 단계를 수동으로 수행하세요."
  echo ""
  echo "  [수동 1단계] Finder에서 아래 파일을 더블클릭하세요:"
  echo "    $SHORTCUT_SRC"
  echo ""
  echo "  더블클릭하면 macOS 단축어 앱이 열리고 임포트 확인 대화상자가 표시됩니다."
  echo ""
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
  echo "============================================================"
  echo "  stashdex 비개발자 키트 설치 (PROJECT_KEY=$PROJECT_KEY)"
  echo "============================================================"
  echo ""

  setup_venv
  echo ""

  ensure_db_up
  echo ""

  install_loregist_symlink
  echo ""

  warmup_model
  echo ""

  ensure_project
  echo ""

  install_launch_agent
  echo ""

  install_command
  echo ""

  guide_shortcut_import

  echo "============================================================"
  echo "  설치 완료."
  echo "============================================================"
}

main "$@"

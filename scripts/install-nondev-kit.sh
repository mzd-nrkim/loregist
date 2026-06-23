#!/usr/bin/env bash
# install-nondev-kit.sh — loregist 비개발자 키트 설치 스크립트
# 사용법: bash scripts/install-nondev-kit.sh
# 멱등(idempotent): 이미 설치된 항목은 스킵하거나 reload만 수행한다.
set -euo pipefail

# ── 기본 변수 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_KEY="personal-work"

LOREGIST_SYMLINK="/usr/local/bin/loregist"
LAUNCH_AGENT_LABEL="io.loregist.auto-embed"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_SRC="$REPO_DIR/scripts/examples/auto-embed.plist"
PLIST_DST="$LAUNCH_AGENT_DIR/${LAUNCH_AGENT_LABEL}.plist"
COMMAND_SRC="$REPO_DIR/scripts/examples/loregist-journal.command"
SHORTCUT_SRC="$REPO_DIR/scripts/examples/loregist-journal.shortcut"
APPS_DIR="$HOME/Applications"
COMMAND_DST="$APPS_DIR/loregist-journal.command"

# ── 출력 헬퍼 ─────────────────────────────────────────────────────────────────
info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*" >&2; }
skip()  { echo "[SKIP]  $*"; }
done_() { echo "[DONE]  $*"; }

# ── C-6: embed 엔진 상태 점검 ─────────────────────────────────────────────────
check_embed_engine() {
  info "C-6: embed 엔진(Docker 컨테이너) 상태 점검 중..."
  if docker ps --filter name=loregist 2>/dev/null | grep -q loregist; then
    done_ "loregist Docker 컨테이너 가동 중."
  else
    warn "loregist Docker 컨테이너가 가동 중이지 않습니다. embed 기능이 동작하지 않을 수 있습니다."
    warn "컨테이너 기동: make db-up  (또는 docker compose -f infra/docker-compose.yml up -d)"
  fi
}

# ── C-2: loregist 바이너리 PATH 등록 / 심링크 ────────────────────────────────
install_loregist_symlink() {
  info "C-2: loregist 심링크 설정 중... (대상: $LOREGIST_SYMLINK)"

  # 실제 바이너리 위치 자동 탐색 — 우선순위: 레포 루트 래퍼 > .venv/bin > homebrew
  local bin_target=""

  # 1) 레포 루트의 래퍼 스크립트
  if [[ -f "$REPO_DIR/loregist" && -x "$REPO_DIR/loregist" ]]; then
    bin_target="$REPO_DIR/loregist"
  fi

  # 2) .venv/bin/loregist (레포 기준)
  if [[ -z "$bin_target" ]]; then
    bin_target="$(find "$REPO_DIR/.venv/bin" -name "loregist" 2>/dev/null | head -1)"
  fi

  # 3) 상위 레포(loregist) .venv/bin/loregist
  if [[ -z "$bin_target" ]]; then
    bin_target="$(find "$REPO_DIR/../loregist/.venv/bin" -name "loregist" 2>/dev/null | head -1)"
  fi

  if [[ -z "$bin_target" ]]; then
    warn "loregist 바이너리를 찾을 수 없습니다. 수동으로 설치 후 재실행하거나 심링크를 직접 생성하세요."
    warn "  예: sudo ln -sf /path/to/loregist $LOREGIST_SYMLINK"
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

  # plist 복사 (ProgramArguments에 /usr/local/bin/loregist가 이미 고정되어 있음)
  # 현재 plist는 `loregist embed`만 있으므로 --project 없이 전체 embed 동작 유지
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
  info "C-4: loregist-journal.command 배치 중..."

  if [[ ! -f "$COMMAND_SRC" ]]; then
    warn ".command 원본 없음: $COMMAND_SRC — 스킵"
    return 0
  fi

  # ~/Applications 디렉터리 생성
  mkdir -p "$APPS_DIR"

  # 원본을 임시 파일로 복사 후 PROJECT_KEY sed 치환, 그 뒤 배치
  local tmp_cmd
  tmp_cmd="$(mktemp /tmp/loregist-journal-XXXXXX.command)"

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
  echo "  loregist 비개발자 키트 설치 (PROJECT_KEY=$PROJECT_KEY)"
  echo "============================================================"
  echo ""

  check_embed_engine
  echo ""

  install_loregist_symlink
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

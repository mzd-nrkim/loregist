#!/usr/bin/env bash
# loregist rotate 전 프로젝트 실행 + 변경 있으면 자동 commit
set -euo pipefail

LOREGIST="${LOREGIST_WORKSPACE:-$HOME/workspace}/loregist/loregist"
TOOLS="${LOREGIST_WORKSPACE:-$HOME/workspace}/tools"
LOG_DIR="${LOREGIST_WORKSPACE:-$HOME/workspace}/logvault/embed-log"
LOG="$LOG_DIR/rotate-$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

{
  echo "=== rotate 시작 $(date) ==="

  for proj in megazone-demo mz-sample loregist util; do
    echo "--- $proj ---"
    "$LOREGIST" rotate --project "$proj" || echo "[WARN] $proj rotate 실패"
  done

  echo "=== git commit ==="
  cd "$TOOLS"
  if git diff --quiet && git diff --staged --quiet; then
    echo "변경 없음, commit 스킵"
  else
    git add -A
    git commit -m "chore(rotate): $(date +%Y-%m-%d) 날짜폴더 → vault 이동"
  fi

  echo "=== 완료 $(date) ==="
} >> "$LOG" 2>&1

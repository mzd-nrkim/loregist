#!/usr/bin/env bash
# loregist rotate 전 프로젝트 실행 + 변경 있으면 자동 commit
set -euo pipefail

LOREGIST="${LOREGIST_DIR:-$HOME/workspace/loregist}/loregist"
TOOLS="${LOREGIST_TOOLS_DIR:-$HOME/workspace/tools}"
LOG_DIR="${LOREGIST_LOG_DIR:-$HOME/workspace/logvault/embed-log}"
LOG="$LOG_DIR/rotate-$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

{
  echo "=== rotate 시작 $(date) ==="

  # 등록 프로젝트를 동적으로 순회 (projects.toml 기준)
  for proj in $("$LOREGIST" projects --json | python3 -c "import sys,json; [print(p['name']) for p in json.load(sys.stdin)]"); do
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

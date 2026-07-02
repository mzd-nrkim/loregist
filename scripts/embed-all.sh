#!/usr/bin/env bash
# stashdex embed 전 프로젝트 실행 (매시간 launchd 잡용)
set -euo pipefail

export STASHDEX_WORKSPACE="${STASHDEX_WORKSPACE:-$HOME/workspace}"
STASHDEX_REPO_DIR="${STASHDEX_REPO_DIR:-$STASHDEX_WORKSPACE/stashdex}"

STASHDEX="$STASHDEX_REPO_DIR/stashdex"

echo "=== embed 시작 $(date) ==="

for proj in $("$STASHDEX" project list | python3 -c "import sys,json; [print(o['name']) for o in json.load(sys.stdin)]"); do
  echo "--- $proj ---"
  "$STASHDEX" embed --incremental --project "$proj" || echo "[WARN] $proj embed 실패"
done

echo "=== 완료 $(date) ==="

#!/bin/bash
# ============================================================
# 키트 역할: 더블클릭 입력 진입점
#   이 파일을 더블클릭하면 macOS 대화창이 열리고,
#   입력한 텍스트가 stashdex journal 명령으로 기록된다.
#
# 최종 배치 위치: ~/Applications/ 또는 바탕화면
#   install-nondev-kit.sh 실행 시 자동 복사·변수 치환된다.
#   수동 설치 시 아래 변수를 직접 수정 후 배치한다.
# ============================================================
set -euo pipefail

# ── 설치 시 sed 치환 대상 변수 ──────────────────────────────────────────────
PROJECT_KEY="personal-work"
LOREGIST_BIN="/usr/local/bin/stashdex"
# ────────────────────────────────────────────────────────────────────────────

# osascript display dialog로 텍스트 입력 받기.
# 취소 버튼 클릭 또는 ESC 시 osascript가 비-0 종료코드를 반환하므로
# 2>/dev/null + || true 조합으로 stderr 억제 후 INPUT을 빈 문자열로 유지.
INPUT=$(osascript -e 'display dialog "기록할 내용을 입력하세요:" with title "로그 기록" default answer "" buttons {"취소", "확인"} default button "확인" cancel button "취소"' 2>/dev/null) || true

# 취소 시 INPUT이 비어 있거나 "text returned:" 토큰이 없으면 조용히 종료
if [[ -z "$INPUT" ]]; then
  exit 0
fi

# "button returned:확인, text returned:<입력값>" 형식에서 text returned: 이후 추출
INPUT="${INPUT#*text returned:}"

# 빈 입력 시 조용히 종료
if [[ -z "$INPUT" ]]; then
  exit 0
fi

# stashdex journal 호출 — INPUT은 항상 이중 따옴표로 인용해 셸 주입 방지
"$LOREGIST_BIN" journal "$INPUT" --project "$PROJECT_KEY"

# 성공 알림
osascript -e 'display notification "기록 완료" with title "stashdex"'

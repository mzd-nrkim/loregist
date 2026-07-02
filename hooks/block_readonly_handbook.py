#!/usr/bin/env python3
"""PreToolUse hook: writable=false handbook 파일 쓰기 차단.

Claude Code가 Edit/Write/NotebookEdit 도구를 호출하기 전에 이 hook이 실행된다.
stdin으로 JSON 입력(tool_name, tool_input)을 받아 tool_input.file_path가
writable=false handbook 경로 집합에 속하면 차단(exit code 2)한다.

차단 집합 구성:
- stashdex.config.PROJECTS 의 모든 프로젝트에 대해 get_readonly_handbook_paths()를
  합집합으로 모은다(파일 경로는 프로젝트 무관하게 유일하므로 안전).
- projects.toml 위치: 이 hook 파일 기준 repo 루트의 projects.toml, 또는
  STASHDEX_PROJECTS_FILE 환경변수로 명시.

과차단 회피 스코핑 (C-2):
- file_path가 없거나 빈 값이면 즉시 통과(허용)
- 차단 집합에 없는 경로는 즉시 통과(허용)
- 대상 도구(Edit/Write/NotebookEdit) 외에는 즉시 통과
- 자동 실행(STASHDEX_AUTO_GUARD 설정 시)일 때만 차단, 대화형 세션은 면제.

차단 규약:
- exit code 2 → Claude Code가 도구 실행을 차단하고 stderr 메시지를 LLM에게 전달
- exit code 0 → 허용 (정상 진행)

오류 발생 시 차단하지 않고(fail-open) stderr에 로그 후 exit 0 한다.
"""

import json
import os
import sys
from pathlib import Path

# stashdex 패키지 경로를 sys.path에 추가 (hook은 임의 cwd에서 실행될 수 있음)
# 워크트리 src를 먼저 등록해 최신 get_readonly_handbook_paths 사용.
# STASHDEX_PROJECTS_FILE 환경변수로 projects.toml 위치를 명시해 경로 mismatch를 방지.
_HOOK_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _HOOK_DIR.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from stashdex import config

# projects.toml 위치를 환경변수로 강제 지정 (미설정이면 기본값 사용)
# 탐색 순서: 환경변수 STASHDEX_PROJECTS_FILE → repo 루트의 projects.toml
_DEFAULT_PROJECTS_TOML = _REPO_ROOT / "projects.toml"

if not os.environ.get("STASHDEX_PROJECTS_FILE"):
    if _DEFAULT_PROJECTS_TOML.exists():
        os.environ["STASHDEX_PROJECTS_FILE"] = str(_DEFAULT_PROJECTS_TOML)

# 차단 대상 도구 집합
_BLOCKED_TOOLS = {"Edit", "Write", "NotebookEdit"}


def _build_blocked_paths():
    """모든 프로젝트의 writable=false handbook 경로를 합집합으로 반환한다.

    Returns:
        set: 정규화된 차단 대상 경로 문자열의 집합
    """
    try:
        from stashdex.config import PROJECTS, get_readonly_handbook_paths
    except Exception as e:
        print(
            "[block_readonly_handbook] stashdex.config 임포트 실패 (fail-open): {}".format(e),
            file=sys.stderr,
        )
        return set()

    blocked = set()
    for project_name in PROJECTS:
        try:
            blocked |= get_readonly_handbook_paths(project_name)
        except Exception as e:
            print(
                "[block_readonly_handbook] 프로젝트 '{}' 경로 수집 실패 (스킵): {}".format(
                    project_name, e
                ),
                file=sys.stderr,
            )
    return blocked


def is_readonly_handbook_path(file_path, blocked_paths):
    """file_path를 realpath 정규화한 뒤 차단 집합과 비교한다.

    Args:
        file_path (str): 검사할 파일 경로
        blocked_paths (set): 차단 대상 정규화 경로 집합

    Returns:
        bool: 차단 대상이면 True
    """
    if not file_path:
        return False
    normalized = os.path.realpath(file_path)
    return normalized in blocked_paths


def main():
    """PreToolUse hook 진입점."""
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw)
    except Exception as e:
        # JSON 파싱 실패 → fail-open
        print(
            "[block_readonly_handbook] stdin JSON 파싱 실패 (fail-open): {}".format(e),
            file=sys.stderr,
        )
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # C-2 스코핑: 대상 도구가 아니면 즉시 통과
    if tool_name not in _BLOCKED_TOOLS:
        sys.exit(0)

    # C-3 스코핑: 자동 무인 실행(stashdex가 spawn한 claude)만 차단 대상.
    # STASHDEX_AUTO_GUARD는 auto_update.launch_headless()가 자식 env에만 주입한다.
    # 미설정 = 사용자 대화 세션 → 사용자 지시 편집은 막지 않는다(통과).
    if not os.environ.get("STASHDEX_AUTO_GUARD"):
        sys.exit(0)

    file_path = tool_input.get("file_path", "")

    # C-2 스코핑: file_path 없으면 즉시 통과
    if not file_path:
        sys.exit(0)

    blocked_paths = _build_blocked_paths()

    # C-2 스코핑: 차단 집합이 비어 있으면(설정 없음) 즉시 통과
    if not blocked_paths:
        sys.exit(0)

    if is_readonly_handbook_path(file_path, blocked_paths):
        normalized = os.path.realpath(file_path)
        print(
            "[stashdex] 차단: '{}' 은 writable=false handbook 파일입니다.\n"
            "  정규화 경로: {}\n"
            "  이 파일은 읽기 전용(writable=false)으로 설정되어 있어 수정할 수 없습니다.\n"
            "  수정이 필요하면 projects.toml 에서 writable=true 로 변경하거나 관리자에게 문의하세요.".format(
                file_path, normalized
            ),
            file=sys.stderr,
        )
        sys.exit(2)  # 차단: Claude Code PreToolUse exit code 2

    # 차단 집합에 없음 → 허용
    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PostToolUse hook: stashdex embed 실행 후 drift 발생 시 handbook 갱신 리마인더 주입.

Claude Code가 Bash 도구로 `stashdex embed`(내용변경성) 명령을 실행한 직후 이 hook이
실행된다. stdin으로 JSON 입력(tool_name, tool_input, tool_response 등)을 받아
drift가 존재하고 세션 안이면 리마인더를 stdout JSON으로 출력한다.

출력 형식 (PostToolUse):
  {"additionalContext": "<리마인더 문자열>"}

출력 없이 exit 0 = 정상 통과 (리마인더 불필요).

예외 안전: 어떠한 예외도 hook 비정상 종료로 사용자 작업을 막지 않도록
전체를 try/except 로 감싸 조용히 통과(stderr 경고만)한다.
"""

import json
import os
import re
import sys
from pathlib import Path

# stashdex 패키지 경로를 sys.path에 추가 (hook은 임의 cwd에서 실행될 수 있음)
_HOOK_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _HOOK_DIR.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# projects.toml 위치를 환경변수로 강제 지정 (미설정이면 기본값 사용)
# 탐색 순서: 환경변수 STASHDEX_PROJECTS_FILE → repo 루트의 projects.toml
_DEFAULT_PROJECTS_TOML = _REPO_ROOT / "projects.toml"

if not os.environ.get("STASHDEX_PROJECTS_FILE"):
    if _DEFAULT_PROJECTS_TOML.exists():
        os.environ["STASHDEX_PROJECTS_FILE"] = str(_DEFAULT_PROJECTS_TOML)

# ─────────────────────────────────────────────────────────────
# 내용변경성 embed 서브커맨드 매칭 패턴 (D-5: 읽기전용 제외)
# stashdex embed ... 만 매칭; search/status/project list 제외
# ─────────────────────────────────────────────────────────────
_EMBED_PATTERN = re.compile(
    r"(?:^|\s)stashdex\s+embed(?:\s|$)",
    re.MULTILINE,
)

# 읽기전용 서브커맨드 패턴 — 이것이 매칭되면 embed이더라도 제외 (방어적 체크)
_READONLY_PATTERN = re.compile(
    r"(?:^|\s)stashdex\s+(?:search|status|project\s+list)(?:\s|$)",
    re.MULTILINE,
)


def _is_content_changing_embed(command: str) -> bool:
    """command가 내용변경성 stashdex embed 호출인지 판정한다.

    - stashdex embed 포함 → True
    - stashdex search / status / project list 포함 → False (읽기전용, D-5)
    - 그 외 → False
    """
    if not _EMBED_PATTERN.search(command):
        return False
    # 방어적으로 읽기전용 패턴이 매칭되면 False
    if _READONLY_PATTERN.search(command):
        return False
    return True


def _parse_project_from_command(command: str) -> "str | None":
    """command 문자열에서 --project <name> 또는 -p <name> 을 추출한다."""
    m = re.search(r"(?:--project|-p)\s+(\S+)", command)
    return m.group(1) if m else None


def decide_reminder(
    tool_name: str,
    command: str,
    in_session: bool,
    drift_count: int,
    handbook_on: bool,
    catalog_on: bool,
) -> "str | None":
    """PostToolUse hook 핵심 판정 순수 함수.

    Parameters
    ----------
    tool_name:
        hook에서 받은 tool_name (Bash 인지 확인)
    command:
        Bash 실행 커맨드 문자열
    in_session:
        CLAUDECODE 환경변수 존재 여부 (True = Claude Code 세션 안)
    drift_count:
        미반영 handbook 파일 수 (0이면 노이즈 차단)
    handbook_on:
        auto_handbook_update 플래그
    catalog_on:
        auto_catalog_update 플래그

    Returns
    -------
    str | None
        리마인더 문자열 또는 None (리마인더 불필요)
    """
    # 1. Bash 도구가 아니면 무시
    if tool_name != "Bash":
        return None

    # 2. 내용변경성 stashdex embed 가 아니면 무시
    if not _is_content_changing_embed(command):
        return None

    # 3. 세션 밖은 무시 (Part C 헤드리스가 처리)
    if not in_session:
        return None

    # 4. drift 없으면 노이즈 차단
    if drift_count == 0:
        return None

    # 5. 플래그 조합 → 진입 스킬 결정
    from stashdex.config import decide_entry_skill

    entry = decide_entry_skill(handbook_on, catalog_on)

    flags_info = (
        f"(auto_handbook_update={'on' if handbook_on else 'off'}, "
        f"auto_catalog_update={'on' if catalog_on else 'off'})"
    )

    if entry is None:
        # 둘 다 off → 제안형
        return (
            f"미반영 handbook {drift_count}개 발견. "
            f"handbook/catalog 갱신도 수행할까요? (승인 시 /wiki-update 실행) "
            f"{flags_info}"
        )
    elif entry == "wiki-update":
        return (
            f"미반영 handbook {drift_count}개. "
            f"auto 플래그(둘 다 on)에 따라 /wiki-update 무인 실행(handbook→catalog 순차). "
            f"내부 승인은 플래그가 대체. {flags_info}"
        )
    elif entry == "catalog-update":
        return (
            f"미반영 handbook {drift_count}개. "
            f"auto_catalog_update=on → /catalog-update 무인 실행(인덱스만, handbook 산문 미수정). "
            f"{flags_info}"
        )
    elif entry == "handbook-update":
        return (
            f"미반영 handbook {drift_count}개. "
            f"auto_handbook_update=on → /handbook-update 무인 실행(산문만). "
            f"{flags_info}"
        )
    else:
        # 알 수 없는 진입점 — 안전하게 제안형으로 fallback
        return (
            f"미반영 handbook {drift_count}개 발견. "
            f"handbook/catalog 갱신도 수행할까요? (승인 시 /{entry} 실행) "
            f"{flags_info}"
        )


def main():
    """PostToolUse hook 진입점."""
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw)
    except Exception as e:
        print(
            "[post_embed_drift] stdin JSON 파싱 실패 (fail-open): {}".format(e),
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""

        # Bash 도구 빠른 필터 (config 로드 전에 체크)
        if tool_name != "Bash":
            sys.exit(0)

        # 내용변경성 embed 빠른 필터
        if not _is_content_changing_embed(command):
            sys.exit(0)

        # 세션 안 여부 (CLAUDECODE 환경변수 존재)
        in_session = bool(os.environ.get("CLAUDECODE"))

        if not in_session:
            sys.exit(0)

        # stashdex config, drift 임포트
        try:
            from stashdex import config
            from stashdex.drift import compute_drift
        except Exception as e:
            print(
                "[post_embed_drift] stashdex 임포트 실패 (fail-open): {}".format(e),
                file=sys.stderr,
            )
            sys.exit(0)

        # 프로젝트 추론
        try:
            explicit_project = _parse_project_from_command(command)
            cwd = os.environ.get("STASHDEX_CWD") or os.getcwd()
            project_name = config.infer_project(cwd=cwd, explicit=explicit_project)
        except Exception as e:
            print(
                "[post_embed_drift] 프로젝트 추론 실패 (fail-open): {}".format(e),
                file=sys.stderr,
            )
            sys.exit(0)

        # drift 계산
        try:
            drift_files = compute_drift(project_name)
            drift_count = len(drift_files)
        except Exception as e:
            print(
                "[post_embed_drift] drift 계산 실패 (fail-open): {}".format(e),
                file=sys.stderr,
            )
            sys.exit(0)

        # 프로젝트 플래그 읽기
        try:
            proj_cfg = config.PROJECTS[project_name]
            handbook_on = bool(proj_cfg.get("auto_handbook_update", False))
            catalog_on = bool(proj_cfg.get("auto_catalog_update", False))
        except Exception as e:
            print(
                "[post_embed_drift] 프로젝트 config 읽기 실패 (fail-open): {}".format(e),
                file=sys.stderr,
            )
            sys.exit(0)

        # 리마인더 판정
        reminder = decide_reminder(
            tool_name=tool_name,
            command=command,
            in_session=in_session,
            drift_count=drift_count,
            handbook_on=handbook_on,
            catalog_on=catalog_on,
        )

        if reminder is not None:
            # PostToolUse hook 출력: stdout으로 JSON {"additionalContext": "..."}
            output = {"additionalContext": reminder}
            print(json.dumps(output, ensure_ascii=False))

    except Exception as e:
        # 최상위 안전망: 어떤 예외도 hook 비정상 종료로 사용자 작업을 막지 않음
        print(
            "[post_embed_drift] 예기치 않은 오류 (fail-open): {}".format(e),
            file=sys.stderr,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()

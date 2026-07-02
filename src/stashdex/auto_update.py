"""
auto_update.py — 헤드리스 Claude 자동 기동 및 사후 리포트 (Phase C+D1)

세션 밖(CLAUDECODE 없음)에서 stashdex embed 실행 후 drift가 있으면
claude -p 를 subprocess로 기동해 handbook/catalog 갱신 스킬을 무인 실행한다.
재귀 기동 방지를 위해 STASHDEX_AUTO_GUARD 환경변수를 자식 프로세스에 주입한다.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess
import sys
from typing import Any

from stashdex.config import decide_entry_skill

logger = logging.getLogger(__name__)


def _resolve_claude_bin() -> str:
    """claude 실행 파일의 절대경로를 해석한다.

    LaunchAgent 등 기본 PATH가 좁은 환경에서 claude를 찾지 못하는 문제를
    방지하기 위해 여러 경로를 순서대로 시도한다.

    해석 우선순위:
    1. STASHDEX_CLAUDE_BIN 환경변수 — 명시적 재정의
    2. shutil.which("claude") — 현재 PATH에 있으면 그 경로
    3. ~/.nvm/versions/node/*/bin/claude glob — nvm 설치 경로 (최신 버전)
    4. /opt/homebrew/bin/claude, /usr/local/bin/claude — Homebrew/전역 설치
    5. 폴백: "claude" (PATH 의존, 기존 동작) + 경고 로그

    Returns
    -------
    str
        claude 실행 파일 경로 또는 "claude" (폴백).
    """
    # 1. 명시적 환경변수
    explicit = os.environ.get("STASHDEX_CLAUDE_BIN")
    if explicit:
        return explicit

    # 2. 현재 PATH에서 탐색
    which_result = shutil.which("claude")
    if which_result:
        return which_result

    # 3. nvm 설치 경로 glob (버전 무관, 존재하는 마지막 = 최신)
    nvm_pattern = os.path.expanduser("~/.nvm/versions/node/*/bin/claude")
    nvm_matches = [p for p in glob.glob(nvm_pattern) if os.path.isfile(p)]
    if nvm_matches:
        return sorted(nvm_matches)[-1]

    # 4. Homebrew / 전역 설치
    for candidate in ("/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        if os.path.isfile(candidate):
            return candidate

    # 5. 폴백: 기존 동작 유지 + 경고
    logger.warning(
        "[auto_update] claude 실행 파일을 찾을 수 없습니다. "
        "PATH에 의존해 기동합니다 — STASHDEX_CLAUDE_BIN 환경변수로 경로를 지정하세요."
    )
    return "claude"


def should_auto_launch(
    env: dict,
    handbook_on: bool,
    catalog_on: bool,
    drift_count: int,
) -> "str | None":
    """헤드리스 Claude 자동 기동 여부를 판정하는 순수 함수.

    3중 조건을 모두 충족해야 entry skill 이름을 반환한다.

    Parameters
    ----------
    env:
        환경변수 딕셔너리 (통상 os.environ).
    handbook_on:
        auto_handbook_update 플래그.
    catalog_on:
        auto_catalog_update 플래그.
    drift_count:
        미반영 handbook 파일 수.

    Returns
    -------
    str | None
        기동할 entry skill 이름, 또는 None(기동 불필요).

    억제 조건 (하나라도 해당하면 None):
    - STASHDEX_AUTO_GUARD 환경변수 존재 → 재귀 가드 (C-3)
    - CLAUDECODE 환경변수 존재 → 세션 안, hook이 처리 (B-4)
    - drift_count == 0 → 갱신 불필요
    - 두 플래그 모두 False → 무인 진입점 없음
    """
    # C-3: 재귀 가드
    if env.get("STASHDEX_AUTO_GUARD"):
        return None

    # B-4: Claude Code 세션 안 — hook이 처리
    if env.get("CLAUDECODE"):
        return None

    # drift 없음
    if drift_count == 0:
        return None

    # 플래그 판정
    entry = decide_entry_skill(handbook_on, catalog_on)
    return entry  # None이면 둘 다 off


def build_claude_command(entry_skill: str, project: str) -> list[str]:
    """claude -p 헤드리스 실행 argv 리스트를 구성한다.

    Parameters
    ----------
    entry_skill:
        실행할 스킬 이름 ("wiki-update" / "handbook-update" / "catalog-update").
    project:
        대상 프로젝트 키.

    Returns
    -------
    list[str]
        subprocess에 넘길 argv 리스트.

    wiki-update는 하위 스킬(handbook-update·catalog-update)을 Agent로 위임하므로
    --allowedTools에 "Agent"를 포함한다. 단일 스킬이면 Agent 제외.
    """
    prompt = f"/{entry_skill} --project {project}"

    if entry_skill == "wiki-update":
        allowed_tools = "Agent,Read,Write,Edit,Bash,Glob,Grep"
    else:
        allowed_tools = "Read,Write,Edit,Bash,Glob,Grep"

    claude_bin = _resolve_claude_bin()

    return [
        claude_bin,
        "-p", prompt,
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
        "--allowedTools", allowed_tools,
    ]


def build_search_command(query: str, folders: list[str]) -> list[str]:
    """파일 agentic 검색용 claude -p argv 리스트를 구성한다.

    Parameters
    ----------
    query:
        검색 쿼리 문자열.
    folders:
        검색 대상 폴더 경로 리스트.

    Returns
    -------
    list[str]
        subprocess에 넘길 argv 리스트.
    """
    prompt = (
        f"다음 폴더들에서 '{query}' 를 검색하고 관련 내용을 찾아 반환하라.\n"
        f"폴더 목록: {', '.join(folders)}\n"
        "각 결과를 다음 JSON 형식으로 반환하라:\n"
        '[{"source_path": "<파일경로>", "score": <0.0~1.0>, "chunk_text": "<관련 텍스트>", "confidence": <0.0~1.0>}]'
    )
    allowed_tools = "Read,Bash,Glob,Grep"
    claude_bin = _resolve_claude_bin()

    return [
        claude_bin,
        "-p", prompt,
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
        "--allowedTools", allowed_tools,
    ]


def launch_headless(entry_skill: str, project: str, cwd: str) -> dict:
    """헤드리스 Claude를 subprocess로 기동하고 결과 dict를 반환한다.

    자식 프로세스 환경에 STASHDEX_AUTO_GUARD=1을 주입해 재귀 기동을 방지한다.
    실행 실패 시 예외를 raise하지 않고 결과 dict에 오류 정보를 담아 반환한다.

    Parameters
    ----------
    entry_skill:
        실행할 스킬 이름.
    project:
        대상 프로젝트 키.
    cwd:
        자식 프로세스의 작업 디렉터리(대상 프로젝트 루트).

    Returns
    -------
    dict
        성공: {"ok": True, "changed_files": [...], "summary": "..."}
        실패: {"ok": False, "error": "...", "drift_surfaced": True}
    """
    argv = build_claude_command(entry_skill, project)

    # C-3: 재귀 가드 주입
    child_env = os.environ.copy()
    child_env["STASHDEX_AUTO_GUARD"] = "1"

    try:
        proc = subprocess.run(
            argv,
            env=child_env,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as exc:
        # claude 실행 파일 없음 등
        msg = f"claude 실행 실패: {exc}"
        print(
            f"[auto_update] {msg} — 수동 갱신 필요 (drift 존재)",
            file=sys.stderr,
        )
        return {"ok": False, "error": msg, "drift_surfaced": True}

    if proc.returncode != 0:
        msg = (
            f"claude 종료 코드 {proc.returncode}: "
            f"{proc.stderr.strip()[:300] if proc.stderr else '(stderr 없음)'}"
        )
        print(
            f"[auto_update] {msg} — 수동 갱신 필요 (drift 존재)",
            file=sys.stderr,
        )
        return {"ok": False, "error": msg, "drift_surfaced": True}

    return parse_report(proc.stdout)


def parse_report(claude_json_stdout: str) -> dict:
    """claude -p --output-format json 출력을 파싱해 변경 요약 dict를 반환한다.

    출력 스키마가 불확실하므로 방어적으로 파싱한다.
    파싱 실패 시 raw 텍스트 앞부분을 summary로 사용한 안전 fallback을 반환한다.

    Parameters
    ----------
    claude_json_stdout:
        claude -p 의 stdout 문자열.

    Returns
    -------
    dict
        {"ok": True, "changed_files": list[str], "summary": str}
    """
    try:
        data = json.loads(claude_json_stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "ok": True,
            "changed_files": [],
            "summary": claude_json_stdout[:500],
        }

    if not isinstance(data, dict):
        return {
            "ok": True,
            "changed_files": [],
            "summary": claude_json_stdout[:500],
        }

    # changed_files: "result" > "files" > "changed_files" 등 여러 키 후보 시도
    changed_files: list[str] = []
    for key in ("changed_files", "files", "modified_files"):
        val = data.get(key)
        if isinstance(val, list):
            changed_files = [str(f) for f in val]
            break

    # summary: "summary" > "result" > "message" > "content" 순으로 시도
    summary = ""
    for key in ("summary", "result", "message", "content"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            summary = val
            break
        if isinstance(val, list) and val:
            # content 배열 형식 대응
            for item in val:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    if text:
                        summary = text
                        break
                elif isinstance(item, str) and item.strip():
                    summary = item
                    break
            if summary:
                break

    return {
        "ok": True,
        "changed_files": changed_files,
        "summary": summary,
    }


def report_log(result: dict, log_target=None) -> None:
    """헤드리스 실행 결과(변경 파일·요약)를 stdout 또는 지정 파일에 기록한다.

    Parameters
    ----------
    result:
        launch_headless() 반환 dict.
    log_target:
        None이면 stdout, 파일 경로 문자열이면 해당 파일에 append.
    """
    lines: list[str] = []

    if result.get("ok"):
        changed = result.get("changed_files", [])
        summary = result.get("summary", "")
        lines.append("[auto_update] 헤드리스 갱신 완료")
        if changed:
            lines.append(f"  변경 파일 ({len(changed)}개):")
            for f in changed:
                lines.append(f"    {f}")
        else:
            lines.append("  변경 파일: 없음")
        if summary:
            lines.append(f"  요약: {summary[:500]}")
    else:
        error = result.get("error", "알 수 없는 오류")
        drift_signal = result.get("drift_surfaced", False)
        lines.append(f"[auto_update] 헤드리스 갱신 실패: {error}")
        if drift_signal:
            lines.append("  → drift가 남아 있습니다. 수동 갱신이 필요합니다.")

    output = "\n".join(lines)

    if log_target is None:
        print(output)
    else:
        with open(log_target, "a", encoding="utf-8") as f:
            f.write(output + "\n")


def git_tracked_changes(cwd: str) -> list[str]:
    """git status --porcelain을 실행해 변경/추적 상태 파일 목록을 반환한다.

    무인 갱신으로 변경된 파일이 git에 추적되는지 확인하여
    사후 감사·롤백이 가능한 상태임을 검증하는 용도로 사용한다.

    Parameters
    ----------
    cwd:
        git 명령을 실행할 작업 디렉터리.

    Returns
    -------
    list[str]
        "XY path" 형식 porcelain 출력의 경로 부분 목록.
        git 미설치 또는 오류 시 빈 리스트.
    """
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return []

    if proc.returncode != 0:
        return []

    result: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) > 3:
            # porcelain 형식: "XY path" (첫 3자는 상태 플래그+공백)
            result.append(line[3:])
    return result

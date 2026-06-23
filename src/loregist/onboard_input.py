"""loregist onboard 입력 수집 / 검증 계층.

onboard.py 에서 분리된 입력 수집·검증 함수 모음.
- 입력 수집: _prompt, _prompt_bare, _ask_key, _ask_type, _ask_path, _ask_catalog, _confirm
- 검증·정규화: _normalize_key, _validate_key, _validate_path, _check_duplicate
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── 상수 ───────────────────────────────────────────────────────
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ── 정규화 / 검증 ───────────────────────────────────────────────

def _normalize_key(name: str) -> str:
    """폴더명을 프로젝트 키 후보로 정규화 (소문자·숫자·하이픈, 공백→하이픈)."""
    s = name.lower()
    s = s.replace(" ", "-")
    # 하이픈·소문자·숫자 이외 문자 제거
    s = re.sub(r"[^a-z0-9-]", "", s)
    # 선두 하이픈 제거
    s = s.lstrip("-")
    return s or "project"


def _validate_key(key: str) -> str | None:
    """키 정규식 검증. 문제 있으면 오류 메시지 반환, 없으면 None."""
    if not key:
        return "프로젝트 키가 비어 있습니다."
    if not _KEY_RE.match(key):
        return f"키 '{key}'가 형식에 맞지 않습니다. ^[a-z0-9][a-z0-9-]*$ 만 허용."
    return None


def _check_duplicate(key: str) -> bool:
    """이미 등록된 키면 True."""
    from loregist.config import load_projects, PROJECTS_FILE
    try:
        projects = load_projects(PROJECTS_FILE)
        return key in projects
    except FileNotFoundError:
        return False


def _validate_path(raw: str, key: str) -> tuple[str, str | None]:
    """
    경로 검증:
    - '..' 포함 거부
    - WORKSPACE 밖 절대경로 거부 (_resolve_path 로 해석 후 is_relative_to 확인)
    반환: (정상화된_경로_문자열, 오류메시지_또는_None)
    """
    from loregist.config import WORKSPACE, _resolve_path
    if ".." in Path(raw).parts:
        return raw, f"경로에 '..'이 포함되어 있습니다: {raw}"
    resolved = _resolve_path(raw)
    if resolved is None:
        return raw, f"경로를 해석할 수 없습니다: {raw}"
    # 절대경로가 WORKSPACE 아래인지 확인
    try:
        resolved.relative_to(WORKSPACE)
    except ValueError:
        # WORKSPACE 밖 절대경로는 거부
        if Path(raw).is_absolute() or raw.startswith("~"):
            return raw, (
                f"WORKSPACE({WORKSPACE}) 밖의 절대경로는 허용되지 않습니다: {raw}"
            )
        # 상대경로는 WORKSPACE 기준 해석이므로 항상 안쪽 — 위에서 통과
    return raw, None


# ── 기본값 추론 ────────────────────────────────────────────────

def _default_key(cwd: Path) -> str:
    return _normalize_key(cwd.name)


def _default_docs_root(cwd: Path, key: str) -> str:
    """cwd 의 WORKSPACE 상대경로(+/dev). 추론 불가 시 tools/personal-work/projects/<키>/dev."""
    from loregist.config import WORKSPACE
    try:
        rel = cwd.relative_to(WORKSPACE)
        return str(rel / "dev")
    except ValueError:
        return f"tools/personal-work/projects/{key}/dev"


def _default_vault(key: str) -> str:
    return f"logvault/{key}"


def _default_cold(key: str) -> str:
    return f"logvault/{key}/cold"


# ── 입력 수집 ───────────────────────────────────────────────────

def _prompt(question: str, default: str, *, is_tty: bool) -> str:
    """TTY 환경에서 `질문 [기본값]: ` 프롬프트. 빈 입력이면 기본값 반환."""
    if not is_tty:
        # 비-TTY: input() 호출 자체를 하지 않고 기본값 반환
        return default
    try:
        ans = input(f"{question} [{default}]: ").strip()
        return ans if ans else default
    except (EOFError, KeyboardInterrupt):
        print("\n중단되었습니다.", file=sys.stderr)
        sys.exit(1)


def _prompt_bare(question: str, *, is_tty: bool, default: str = "") -> str:
    """기본값 없는 자유 입력 프롬프트."""
    if not is_tty:
        return default
    try:
        ans = input(f"{question}: ").strip()
        return ans
    except (EOFError, KeyboardInterrupt):
        print("\n중단되었습니다.", file=sys.stderr)
        sys.exit(1)


def _ask_key(flag_project: str | None, *, is_tty: bool, cwd: Path) -> str:
    """(B-1, B-3) 프로젝트 키 문답 + 검증 루프."""
    default = _normalize_key(cwd.name)
    if flag_project is not None:
        key = flag_project
        err = _validate_key(key)
        if err:
            print(f"[오류] {err}", file=sys.stderr)
            sys.exit(1)
        if _check_duplicate(key):
            print(f"[오류] 프로젝트 키 '{key}'가 이미 등록되어 있습니다.", file=sys.stderr)
            sys.exit(1)
        return key

    while True:
        key = _prompt("프로젝트 키(영소문자·숫자·하이픈)", default, is_tty=is_tty)
        err = _validate_key(key)
        if err:
            if not is_tty:
                print(f"[오류] {err}", file=sys.stderr)
                sys.exit(1)
            print(f"  {err}", file=sys.stderr)
            continue
        if _check_duplicate(key):
            msg = f"프로젝트 키 '{key}'가 이미 등록되어 있습니다."
            if not is_tty:
                print(f"[오류] {msg}", file=sys.stderr)
                sys.exit(1)
            print(f"  {msg}", file=sys.stderr)
            continue
        return key


def _ask_type(flag_type: str | None, *, is_tty: bool) -> str:
    """(B-1) 프로젝트 유형 선택. docs_root | done."""
    if flag_type is not None:
        if flag_type not in ("docs_root", "done"):
            print(f"[오류] --type 은 docs_root 또는 done 만 허용합니다.", file=sys.stderr)
            sys.exit(1)
        return flag_type
    default = "docs_root"
    while True:
        raw = _prompt("유형(docs_root=일반 문서형 / done=완료문서 이관형)", default, is_tty=is_tty)
        if raw in ("docs_root", "done"):
            return raw
        if not is_tty:
            print(f"[오류] 유형은 docs_root 또는 done 만 허용합니다.", file=sys.stderr)
            sys.exit(1)
        print("  'docs_root' 또는 'done' 으로 입력하세요.", file=sys.stderr)


def _ask_path(
    label: str,
    flag_val: str | None,
    default: str,
    *,
    is_tty: bool,
    required: bool = True,
) -> str:
    """경로 문답 + 검증 루프."""
    if flag_val is not None:
        val = flag_val
        _, err = _validate_path(val, label)
        if err:
            print(f"[오류] {err}", file=sys.stderr)
            sys.exit(1)
        return val

    while True:
        if required or default:
            val = _prompt(label, default, is_tty=is_tty)
        else:
            val = _prompt_bare(label, is_tty=is_tty, default=default)
            if not val:
                return val
        if not val:
            if not is_tty:
                print(f"[오류] {label} 값이 필요합니다.", file=sys.stderr)
                sys.exit(1)
            print(f"  경로를 입력하세요.", file=sys.stderr)
            continue
        _, err = _validate_path(val, label)
        if err:
            if not is_tty:
                print(f"[오류] {err}", file=sys.stderr)
                sys.exit(1)
            print(f"  {err}", file=sys.stderr)
            continue
        return val


def _ask_catalog(flag_catalog: bool | None, *, is_tty: bool) -> bool:
    """(B-1) catalog opt-in 여부. 기본 no."""
    if flag_catalog is not None:
        return flag_catalog
    default = "no"
    while True:
        raw = _prompt("catalog opt-in(yes/no) — _catalog/ 자동 생성", default, is_tty=is_tty)
        if raw.lower() in ("yes", "y"):
            return True
        if raw.lower() in ("no", "n", ""):
            return False
        if not is_tty:
            return False
        print("  'yes' 또는 'no' 로 입력하세요.", file=sys.stderr)


def _confirm(summary_lines: list[str], *, yes: bool, is_tty: bool) -> bool:
    """(B-1) 요약 표 출력 후 진행 확인. --yes 또는 비-TTY면 자동 진행."""
    for line in summary_lines:
        print(line)
    if yes or not is_tty:
        return True
    try:
        ans = input("\n진행할까요? [Y/n]: ").strip()
        return ans.lower() in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print("\n중단되었습니다.", file=sys.stderr)
        return False


def _build_summary(
    key: str,
    proj_type: str,
    docs_root: str | None,
    vault: str,
    cold_or_done: str,
    catalog: bool,
) -> list[str]:
    """요약 테이블 문자열 목록 반환."""
    lines = [
        "",
        "─" * 50,
        "  등록 내용 요약",
        "─" * 50,
        f"  키(name)   : {key}",
        f"  유형       : {proj_type}",
    ]
    if proj_type == "docs_root":
        lines.append(f"  docs_root  : {docs_root}")
        lines.append(f"  vault      : {vault}")
        lines.append(f"  cold       : {cold_or_done}")
    else:
        lines.append(f"  vault      : {vault}")
        lines.append(f"  done       : {cold_or_done}")
    lines.append(f"  catalog    : {'yes (_catalog/ 초기화)' if catalog else 'no'}")
    lines.append("─" * 50)
    return lines


def _print_summary(
    key: str,
    proj_type: str,
    docs_root: str | None,
    vault: str,
    cold_or_done: str,
    catalog: bool,
    created_dirs: list[Path],
    catalog_ok: bool,
    embed_ok: bool,
    applied_stages: list[str],
) -> None:
    """(C-4, C-5) 완료 요약 출력."""
    from loregist.config import _resolve_path
    print()
    print("=" * 50)
    print(f"  프로젝트 '{key}' 등록 완료")
    print("=" * 50)
    print(f"  등록 키   : {key}")
    print(f"  유형      : {proj_type}")
    if proj_type == "docs_root" and docs_root:
        dr = _resolve_path(docs_root)
        print(f"  docs_root : {dr}")
    vp = _resolve_path(vault)
    print(f"  vault     : {vp}")
    cod = _resolve_path(cold_or_done) if cold_or_done else None
    label = "cold" if proj_type == "docs_root" else "done"
    if cod:
        print(f"  {label:<9} : {cod}")
    if catalog:
        print(f"  catalog   : 초기화됨 ({'성공' if catalog_ok else '실패'})")

    print()
    print("  적용된 단계:")
    for stage in applied_stages:
        print(f"    {stage}")

    if not embed_ok:
        print()
        print("  [주의] embed 단계가 실패했습니다.")
        print("  projects.toml 등록과 디렉터리 생성은 완료되었습니다.")
        print(f"  나중에 수동으로 실행하세요: loregist embed --project {key}")

    print()
    print("  다음 단계:")
    print(f"    loregist journal      # 새 작업 일지 작성")
    print(f"    loregist search <쿼리> --project {key}  # 문서 검색")
    print()

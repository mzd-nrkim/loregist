"""loregist project add — 문답형 온보딩 마법사.

사용법:
    loregist project add                            # 인터랙티브(TTY)
    loregist project add --project myproj --yes     # 기본값으로 빠른 진행
    loregist project add --project myproj --type docs_root \\
        --docs-root tools/my/dev --vault logvault/my --yes   # 비대화(스크립트)

B-1~B-4: argparse + 문답 루프, cwd 기반 기본값, 입력 검증, 비-TTY 가드
C-1~C-5: projects.toml 블록 append, 디렉터리 생성, catalog init, embed, 중간 실패 처리
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# ── 입력 수집 / 검증 계층 import ─────────────────────────────────
from loregist.onboard_input import (
    _default_docs_root,
    _default_vault,
    _default_cold,
    _ask_key,
    _ask_type,
    _ask_path,
    _ask_catalog,
    _confirm,
    _build_summary,
    _print_summary,
)

# ── 상수 ───────────────────────────────────────────────────────

# TOML 블록 템플릿 — docs_root형(docs_root + vault + cold)
_TOML_DOCS_ROOT = """\

[projects.{key}]
docs_root = "{docs_root}"
vault     = "{vault}"
cold      = "{cold}"
"""

# TOML 블록 템플릿 — docs_root형 + catalog
_TOML_DOCS_ROOT_CATALOG = """\

[projects.{key}]
docs_root = "{docs_root}"
vault     = "{vault}"
cold      = "{cold}"
catalog   = true
"""

# TOML 블록 템플릿 — done형(vault + done)
_TOML_DONE = """\

[projects.{key}]
vault = "{vault}"
done  = "{done}"
"""

# TOML 블록 템플릿 — done형 + catalog
_TOML_DONE_CATALOG = """\

[projects.{key}]
vault   = "{vault}"
done    = "{done}"
catalog = true
"""


# ── 헬퍼 ───────────────────────────────────────────────────────

def _build_toml_block(
    key: str,
    proj_type: str,
    docs_root: str | None,
    vault: str,
    cold_or_done: str,
    catalog: bool,
) -> str:
    """유형별 TOML 블록 문자열 생성."""
    if proj_type == "docs_root":
        tmpl = _TOML_DOCS_ROOT_CATALOG if catalog else _TOML_DOCS_ROOT
        return tmpl.format(key=key, docs_root=docs_root, vault=vault, cold=cold_or_done)
    else:
        tmpl = _TOML_DONE_CATALOG if catalog else _TOML_DONE
        return tmpl.format(key=key, vault=vault, done=cold_or_done)


def _append_toml(key: str, block: str) -> None:
    """(C-1) projects.toml 끝에 블록 append. 실행 직전 중복 키 재확인."""
    from loregist.config import PROJECTS_FILE, load_projects
    # 실행 직전 재확인
    try:
        existing = load_projects(PROJECTS_FILE)
        if key in existing:
            raise ValueError(f"프로젝트 키 '{key}'가 이미 등록되어 있습니다 (재확인 실패).")
    except FileNotFoundError:
        pass

    with open(PROJECTS_FILE, "a", encoding="utf-8") as f:
        f.write(block)


def _create_dirs(proj_type: str, docs_root: str | None, vault: str, cold_or_done: str) -> list[Path]:
    """(C-2) 필요한 디렉터리 생성. 생성된 경로 목록 반환."""
    from loregist.config import _resolve_path
    created: list[Path] = []

    if proj_type == "docs_root" and docs_root:
        dr = _resolve_path(docs_root)
        if dr:
            for sub in (dr, dr / "dev", dr / "etc"):
                sub.mkdir(parents=True, exist_ok=True)
                created.append(sub)

    vault_path = _resolve_path(vault)
    if vault_path:
        vault_path.mkdir(parents=True, exist_ok=True)
        created.append(vault_path)

    # cold 또는 done 경로도 생성
    if cold_or_done:
        cod_path = _resolve_path(cold_or_done)
        if cod_path:
            cod_path.mkdir(parents=True, exist_ok=True)
            created.append(cod_path)

    return created


def _run_catalog_init(key: str) -> int:
    """(C-3) catalog_gen init --project <키> 실행. 종료코드 반환."""
    result = subprocess.run(
        [sys.executable, "-m", "loregist.catalog_gen", "init", "--project", key],
        capture_output=False,
    )
    return result.returncode


def _run_embed(key: str) -> int:
    """(C-4) embed --project <키> 실행. 종료코드 반환."""
    result = subprocess.run(
        [sys.executable, "-m", "loregist.embed", "--project", key],
        capture_output=False,
    )
    return result.returncode


# ── 메인 진입점 ───────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """문답형 온보딩 마법사 진입점.

    project_cmd.py 의 add 핸들러가 `onboard.main(argv)` 로 호출한다.
    """
    parser = argparse.ArgumentParser(
        prog="loregist project add",
        description="새 프로젝트를 문답형으로 온보딩한다.",
    )
    parser.add_argument("--project", help="프로젝트 키 (기본: cwd 폴더명 정규화)")
    parser.add_argument(
        "--type",
        choices=["docs_root", "done"],
        default=None,
        help="프로젝트 유형 — docs_root(일반 문서형) 또는 done(완료문서 이관형). 기본: docs_root",
    )
    parser.add_argument("--docs-root", dest="docs_root", help="docs_root 경로 (docs_root형 전용)")
    parser.add_argument("--vault", help="vault 경로")
    parser.add_argument("--cold", help="cold 경로 (docs_root형 전용)")
    parser.add_argument("--done", dest="done", help="done 경로 (done형 전용)")
    # --catalog / --no-catalog 으로 명시적 yes/no 가능, 미지정 시 None → 문답으로 결정
    catalog_group = parser.add_mutually_exclusive_group()
    catalog_group.add_argument(
        "--catalog",
        dest="catalog",
        action="store_true",
        default=None,
        help="catalog opt-in (_catalog/ 초기화)",
    )
    catalog_group.add_argument(
        "--no-catalog",
        dest="catalog",
        action="store_false",
        help="catalog opt-out (기본값)",
    )
    parser.set_defaults(catalog=None)
    parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="확인 프롬프트 건너뜀 (기본값/플래그값으로 자동 진행)",
    )

    args = parser.parse_args(argv)

    # ── B-4: 비-TTY 가드 ──────────────────────────────────────
    is_tty = sys.stdin.isatty()

    # 비-TTY 에서 필수값 점검
    if not is_tty:
        missing = []
        if args.project is None:
            missing.append("--project")
        if args.type is None and args.docs_root is None and args.vault is None:
            # 완전히 미지정이면 유형 판별 불가
            pass  # 기본값(docs_root)으로 진행 가능
        if missing:
            print(
                f"[오류] 비-TTY 모드에서 필수 옵션이 없습니다: {', '.join(missing)}",
                file=sys.stderr,
            )
            parser.print_usage(sys.stderr)
            return 1

    cwd = Path.cwd()

    # ── B-1 ~ B-3: 7단계 문답 ────────────────────────────────

    # 1. 키
    key = _ask_key(args.project, is_tty=is_tty, cwd=cwd)

    # 2. 유형
    proj_type = _ask_type(args.type, is_tty=is_tty)

    # 3. docs_root (docs_root형만)
    docs_root: str | None = None
    if proj_type == "docs_root":
        dr_default = _default_docs_root(cwd, key)
        docs_root = _ask_path(
            "docs_root 경로",
            args.docs_root,
            dr_default,
            is_tty=is_tty,
        )

    # 4. vault
    vault_default = _default_vault(key)
    vault = _ask_path("vault 경로", args.vault, vault_default, is_tty=is_tty)

    # 5. cold (docs_root형) / done (done형)
    if proj_type == "docs_root":
        cold_default = _default_cold(key)
        cold_or_done = _ask_path("cold 경로", args.cold, cold_default, is_tty=is_tty)
    else:
        # done형: done 경로 — 예시 힌트 포함, 비-TTY에서 --done 필수
        if not is_tty and args.done is None:
            print("[오류] done형에서 --done 경로가 필요합니다.", file=sys.stderr)
            return 1
        done_default = args.done or ""
        if is_tty and not done_default:
            done_default = f"{key}/plans/done"
        cold_or_done = _ask_path(
            "done 경로 (예: <repo>/plans/done)",
            args.done,
            done_default,
            is_tty=is_tty,
            required=True,
        )

    # 6. catalog opt-in
    catalog = _ask_catalog(args.catalog, is_tty=is_tty)

    # 7. 요약 확인
    summary_lines = _build_summary(key, proj_type, docs_root, vault, cold_or_done, catalog)
    if not _confirm(summary_lines, yes=args.yes, is_tty=is_tty):
        print("취소되었습니다.", file=sys.stderr)
        return 1

    # ── C: 실행 오케스트레이션 ────────────────────────────────
    applied_stages: list[str] = []

    # C-1: projects.toml 블록 append
    print("\n[1/4] projects.toml 블록 추가...")
    try:
        block = _build_toml_block(key, proj_type, docs_root, vault, cold_or_done, catalog)
        _append_toml(key, block)
        applied_stages.append("[OK] A. projects.toml 블록 append")
        print(f"  [OK] 블록 추가 완료")
    except Exception as e:
        print(f"  [오류] projects.toml 쓰기 실패: {e}", file=sys.stderr)
        print("  어디까지 적용됨: 없음 (projects.toml 미수정)", file=sys.stderr)
        return 1

    # C-2: 디렉터리 생성
    print("[2/4] 디렉터리 생성...")
    try:
        created_dirs = _create_dirs(proj_type, docs_root, vault, cold_or_done)
        applied_stages.append(f"[OK] B. 디렉터리 생성 ({len(created_dirs)}개)")
        for d in created_dirs:
            print(f"  mkdir: {d}")
    except Exception as e:
        print(f"  [오류] 디렉터리 생성 실패: {e}", file=sys.stderr)
        print(
            "  어디까지 적용됨:\n"
            f"    - projects.toml 블록 추가 완료\n"
            f"    - 디렉터리 생성 실패 (부분 생성 가능)",
            file=sys.stderr,
        )
        applied_stages.append(f"[FAIL] B. 디렉터리 생성 실패: {e}")
        # 디렉터리 실패는 계속 진행하지 않음
        return 1

    # C-3: catalog init
    catalog_ok = True
    if catalog:
        print("[3/4] catalog 초기화...")
        rc = _run_catalog_init(key)
        if rc != 0:
            catalog_ok = False
            applied_stages.append(f"[FAIL] C. catalog init 실패 (exit {rc})")
            print(f"  [경고] catalog init 실패 (exit {rc}). 수동으로 실행하세요:", file=sys.stderr)
            print(f"    loregist catalog-init --project {key}", file=sys.stderr)
        else:
            applied_stages.append("[OK] C. catalog init")
    else:
        applied_stages.append("[SKIP] C. catalog opt-out")

    # C-4: 초기 embed
    print("[4/4] 초기 embed 실행...")
    embed_ok = True
    embed_rc = _run_embed(key)
    if embed_rc != 0:
        embed_ok = False
        applied_stages.append(f"[FAIL] D. embed 실패 (exit {embed_rc})")
    else:
        applied_stages.append("[OK] D. embed 완료")

    # 완료 요약
    _print_summary(
        key,
        proj_type,
        docs_root,
        vault,
        cold_or_done,
        catalog,
        created_dirs,
        catalog_ok,
        embed_ok,
        applied_stages,
    )

    return 0 if embed_ok else 2


if __name__ == "__main__":
    sys.exit(main())

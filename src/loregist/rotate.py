#!/usr/bin/env python
"""
lifecycle_rotate.py — repo docs/dev/ → vault 이동 (C 항목)

날짜 폴더(YYYY-MM-DD) 중 ROTATE_TO_VAULT_DAYS 초과 경과한 폴더의 .md 파일을
임베딩 확인 후 vault로 이동하고 repo 측은 git rm 으로 제거한다.
vault 삭제는 절대 하지 않음 (E 항목 일원화).

cold는 rotate 비대상 — 이미 cold storage에 있는 종착지 파일이므로 재이동하지 않는다.
rotate 원: done(plans/done/) → 목적지: vault/cold/
"""
import argparse
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from loregist.config import PROJECTS, ROTATE_TO_VAULT_DAYS, get_db_connection, infer_project


# ---------------------------------------------------------------------------
# C-6. 날짜 폴더 파싱
# ---------------------------------------------------------------------------

def parse_folder_date(name: str) -> date | None:
    """폴더명 YYYY-MM-DD → date. 파싱 불가 시 None 반환."""
    try:
        return datetime.strptime(name, "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# C-1. 이동 대상 파일 수집
# ---------------------------------------------------------------------------

def discover_rotate_targets(project: str) -> list[tuple[Path, int]]:
    """
    PROJECTS[project]['docs_root'] 하위 날짜 폴더를 스캔해
    ROTATE_TO_VAULT_DAYS 초과 경과된 폴더의 *.md 파일 목록을 반환한다.
    반환: [(파일 Path, 경과일수), ...]
    _catalog / 오늘 폴더는 제외.
    """
    cfg = PROJECTS[project]
    docs_root: Path | None = cfg.get("docs_root")
    if not docs_root or not docs_root.exists():
        print(f"[WARN] {project}: docs_root 가 없거나 존재하지 않음, 스캔 건너뜀", file=sys.stderr)
        return []

    today = date.today()
    results: list[tuple[Path, int]] = []

    for entry in sorted(docs_root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name in ("_catalog",):  # cold 폴더는 discover_rotate_targets 스캔 밖 (docs_root 아님)
            continue

        folder_date = parse_folder_date(name)
        if folder_date is None:
            print(f"[WARN] 날짜 폴더 파싱 불가, 스킵: {entry}", file=sys.stderr)
            continue

        if folder_date == today:
            continue  # 오늘 폴더 제외

        elapsed = (today - folder_date).days
        if elapsed < ROTATE_TO_VAULT_DAYS:
            continue  # 아직 기간 미경과

        for md_file in sorted(entry.rglob("*.md")):
            results.append((md_file, elapsed))

    return results


def discover_done_rotate_targets(project: str) -> list[tuple[Path, int]]:
    """
    done 경로에서 파일명 YYYY-MM-DD로 시작하는 *.md를 스캔해
    ROTATE_TO_VAULT_DAYS 초과 경과된 파일 목록을 반환한다.
    반환: [(파일 Path, 경과일수), ...]
    cold 경로는 rotate 비대상 — 이미 cold storage 종착지.
    """
    cfg = PROJECTS[project]
    done: Path | None = cfg.get("done")
    if not done or not done.exists():
        return []

    today = date.today()
    results: list[tuple[Path, int]] = []

    for md_file in sorted(done.glob("*.md")):
        file_date = parse_folder_date(md_file.name[:10])
        if file_date is None:
            continue  # 날짜 접두사 없는 파일 스킵

        if file_date == today:
            continue

        elapsed = (today - file_date).days
        if elapsed < ROTATE_TO_VAULT_DAYS:
            continue

        results.append((md_file, elapsed))

    return results


# ---------------------------------------------------------------------------
# C-2. 임베딩 확인
# ---------------------------------------------------------------------------

def is_embedded(conn, project: str, path: Path) -> bool:
    """doc_originals 에 해당 파일의 임베딩 레코드가 있으면 True."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM doc_originals WHERE project = %s AND source_path = %s",
        (project, str(path)),
    )
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# C-5. git rm
# ---------------------------------------------------------------------------

def _find_repo_root(docs_root: Path) -> Path:
    """docs_root 상위를 순회해 .git 이 있는 첫 번째 디렉터리를 repo_root 로 반환."""
    candidate = docs_root
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    raise FileNotFoundError(f".git 디렉터리를 찾을 수 없음: {docs_root} 상위 탐색 실패")


def git_rm(repo_root: Path, file_path: Path) -> bool:
    """
    repo 측 파일을 git rm 으로 제거한다.
    git 추적 파일이 아니면 경고만 출력하고 False 반환.
    성공 시 True 반환.
    """
    rel = file_path.relative_to(repo_root)
    # 추적 여부 확인
    check = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", str(rel)],
        capture_output=True,
    )
    if check.returncode != 0:
        print(
            f"[WARN] git 추적 파일 아님, git rm 건너뜀 (파일은 이미 vault로 이동됨): {file_path}",
            file=sys.stderr,
        )
        return False

    result = subprocess.run(
        ["git", "-C", str(repo_root), "rm", str(rel)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"[ERROR] git rm 실패 ({rel}): {result.stderr.strip()}",
            file=sys.stderr,
        )
        return False

    return True


# ---------------------------------------------------------------------------
# C-1 (계속). 단일 파일 이동
# ---------------------------------------------------------------------------

def _do_rotate(src: Path, dst: Path, repo_anchor: Path, label: str) -> bool:
    """
    src → dst 복사, repo_anchor 기준 git rm, 결과 출력.
    성공 시 True, 실패 시 False 반환.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    try:
        repo_root = _find_repo_root(repo_anchor)
    except FileNotFoundError as e:
        print(f"[ERROR] repo root 탐색 실패: {e}", file=sys.stderr)
        return False

    git_rm(repo_root, src)
    print(f"{label} {src} → {dst}")
    return True


def rotate_file(src: Path, project: str) -> bool:
    """
    src 파일을 vault 로 이동하고 repo 측을 git rm 한다.
    vault 경로가 None 이면 스킵.
    성공 시 True, 스킵/실패 시 False 반환.
    """
    cfg = PROJECTS[project]
    vault: Path | None = cfg.get("vault")
    if vault is None:
        print(f"[WARN] {project}: vault 경로가 None, 이동 불가 → 스킵: {src}", file=sys.stderr)
        return False

    docs_root: Path = cfg["docs_root"]

    # vault 내 상대 경로 보존
    rel = src.relative_to(docs_root)
    dst = vault / rel

    return _do_rotate(src, dst, docs_root, "[ROTATE]")


def rotate_done_file(src: Path, project: str) -> bool:
    """
    done 파일을 vault/cold/ 로 이동하고 repo 측을 git rm 한다.
    vault 경로가 None 이면 스킵.
    """
    cfg = PROJECTS[project]
    vault: Path | None = cfg.get("vault")
    if vault is None:
        print(f"[WARN] {project}: vault 경로가 None → 스킵: {src}", file=sys.stderr)
        return False

    done: Path = cfg["done"]
    dst = vault / "cold" / src.name

    return _do_rotate(src, dst, done, "[ROTATE-DONE]")


# ---------------------------------------------------------------------------
# C-3. dry-run 출력 + main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="docs/dev/ 날짜 폴더 → vault 이동 (라이프사이클 C)"
    )
    parser.add_argument("--project", help="프로젝트명 (기본: cwd 추론)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="이동 대상 목록과 경과일·임베딩 여부만 출력, 파일시스템/git 변경 없음",
    )
    args = parser.parse_args()

    project = infer_project(explicit=args.project)
    if project not in PROJECTS:
        print(
            f"오류: 미등록 프로젝트 '{project}'. vector_config.py 의 PROJECTS 에 추가하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"프로젝트: {project}  (rotate 기준: {ROTATE_TO_VAULT_DAYS}일 초과)")

    targets = discover_rotate_targets(project)
    done_targets = discover_done_rotate_targets(project)
    if not targets and not done_targets:
        print("이동 대상 파일 없음.")
        return

    print(f"이동 대상: {len(targets) + len(done_targets)}개 (날짜폴더={len(targets)}, done={len(done_targets)})")

    if args.dry_run:
        with get_db_connection() as conn:
            for file_path, elapsed in targets:
                embedded = is_embedded(conn, project, file_path)
                embed_mark = "O" if embedded else "X"
                print(f"  [경과={elapsed}일] [임베딩={embed_mark}] {file_path}")
            for file_path, elapsed in done_targets:
                embedded = is_embedded(conn, project, file_path)
                embed_mark = "O" if embedded else "X"
                print(f"  [done] [경과={elapsed}일] [임베딩={embed_mark}] {file_path.name}")
        return

    # 실제 이동
    rotated = 0
    skipped = 0
    errors = 0

    with get_db_connection() as conn:
        for file_path, elapsed in targets:
            if not is_embedded(conn, project, file_path):
                print(
                    f"[SKIP] 원문 미임베딩, 먼저 embed 필요: {file_path}",
                    file=sys.stderr,
                )
                skipped += 1
                continue

            ok = rotate_file(file_path, project)
            if ok:
                rotated += 1
            else:
                errors += 1

        for file_path, elapsed in done_targets:
            if not is_embedded(conn, project, file_path):
                print(f"[SKIP] 원문 미임베딩: {file_path.name}", file=sys.stderr)
                skipped += 1
                continue
            ok = rotate_done_file(file_path, project)
            if ok:
                rotated += 1
            else:
                errors += 1

    print(
        f"완료: 이동={rotated}개, 스킵(미임베딩)={skipped}개, 오류={errors}개"
    )


if __name__ == "__main__":
    main()

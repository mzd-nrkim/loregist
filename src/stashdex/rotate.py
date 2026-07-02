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
import os
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from stashdex.config import DEFAULT_EXTENSIONS, PROJECTS, get_db_connection, infer_project

_IGNORE_FOR_EMPTY: frozenset[str] = frozenset({".DS_Store", ".gitkeep"})


# ---------------------------------------------------------------------------
# CLI 헬퍼
# ---------------------------------------------------------------------------

def _parse_extensions(raw: str | None) -> list[str] | None:
    """
    CLI --extensions 값을 정규화된 확장자 리스트로 변환한다.

    - raw가 None이면 None 반환 (toml/기본값 폴백 신호).
    - 쉼표 또는 공백으로 split → strip → 앞쪽 '.' 제거 → 소문자화 → 빈 토큰 제거.
    - 정규화 후 항목이 0개면 None 반환 (toml/기본값 폴백).
    """
    if raw is None:
        return None
    import re
    tokens = re.split(r"[,\s]+", raw)
    cleaned = [t.lstrip(".").lower() for t in tokens if t.strip()]
    return cleaned if cleaned else None


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

def discover_rotate_targets(project: str, extensions: list[str] | None = None) -> list[tuple[Path, int]]:
    """
    PROJECTS[project]['docs_root'] 하위 날짜 폴더를 스캔해
    ROTATE_TO_VAULT_DAYS 초과 경과된 폴더의 extensions 대상 확장자 파일 목록을 반환한다.
    반환: [(파일 Path, 경과일수), ...]
    _wiki / 오늘 폴더는 제외.

    확장자 정책: extensions 파라미터 또는 PROJECTS[project]['extensions'] 기본값 사용.
    기본값은 ["md", "log", "txt"].
    """
    cfg = PROJECTS[project]
    docs_root: Path | None = cfg.get("docs_root")
    if not docs_root or not docs_root.exists():
        print(f"[WARN] {project}: docs_root 가 없거나 존재하지 않음, 스캔 건너뜀", file=sys.stderr)
        return []

    if extensions is None:
        extensions = cfg.get("extensions", DEFAULT_EXTENSIONS)

    today = date.today()
    results: list[tuple[Path, int]] = []

    for entry in sorted(docs_root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name in ("_wiki",):  # cold 폴더는 discover_rotate_targets 스캔 밖 (docs_root 아님)
            continue

        folder_date = parse_folder_date(name)
        if folder_date is None:
            print(f"[WARN] 날짜 폴더 파싱 불가, 스킵: {entry}", file=sys.stderr)
            continue

        if folder_date == today:
            continue  # 오늘 폴더 제외

        elapsed = (today - folder_date).days
        if elapsed < cfg["hot_days"]:
            continue  # 아직 기간 미경과

        seen: set[Path] = set()
        files: list[Path] = []
        for ext in extensions:
            for f in sorted(entry.rglob(f"*.{ext}")):
                if f not in seen:
                    seen.add(f)
                    files.append(f)
        for md_file in sorted(files):
            results.append((md_file, elapsed))

    return results


def discover_done_rotate_targets(project: str, extensions: list[str] | None = None) -> list[tuple[Path, int]]:
    """
    done 경로에서 파일명 YYYY-MM-DD로 시작하는 extensions 대상 확장자 파일을 스캔해
    ROTATE_TO_VAULT_DAYS 초과 경과된 파일 목록을 반환한다.
    반환: [(파일 Path, 경과일수), ...]
    cold 경로는 rotate 비대상 — 이미 cold storage 종착지.

    확장자 정책: extensions 파라미터 또는 PROJECTS[project]['extensions'] 기본값 사용.
    기본값은 ["md", "log", "txt"].
    """
    cfg = PROJECTS[project]
    done: Path | None = cfg.get("done")
    if not done or not done.exists():
        return []

    if extensions is None:
        extensions = cfg.get("extensions", DEFAULT_EXTENSIONS)

    today = date.today()
    results: list[tuple[Path, int]] = []

    seen: set[Path] = set()
    files: list[Path] = []
    for ext in extensions:
        for f in sorted(done.glob(f"*.{ext}")):
            if f not in seen:
                seen.add(f)
                files.append(f)

    for md_file in sorted(files):
        file_date = parse_folder_date(md_file.name[:10])
        if file_date is None:
            continue  # 날짜 접두사 없는 파일 스킵

        if file_date == today:
            continue

        elapsed = (today - file_date).days
        if elapsed < cfg["hot_days"]:
            continue

        results.append((md_file, elapsed))

    return results


# ---------------------------------------------------------------------------
# E-3. 빈 날짜폴더 정리 헬퍼
# ---------------------------------------------------------------------------

def _is_content_empty(folder: Path) -> bool:
    """폴더 내 콘텐츠 파일이 없는지 확인 (메타파일 무시)."""
    for p in folder.iterdir():
        if p.name not in _IGNORE_FOR_EMPTY:
            return False
    return True


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
            f"[WARN] git 추적 파일 아님, git rm 건너뜀 (git 미추적 파일, os.remove로 직접 삭제 시도): {file_path}",
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

    if not git_rm(repo_root, src):
        try:
            os.remove(src)
        except OSError as e:
            print(f"[WARN] os.remove 실패 (원본 제거 불가): {src}: {e}", file=sys.stderr)
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
# P-4-1. 다음달 파티션 자동 생성
# ---------------------------------------------------------------------------

def ensure_next_month_partition(conn) -> None:
    """다음달 파티션이 없으면 자동 생성한다."""
    from datetime import date
    today = date.today()
    # 다음달 계산
    if today.month == 12:
        next_year, next_month = today.year + 1, 1
    else:
        next_year, next_month = today.year, today.month + 1

    partition_name = f"doc_chunks_{next_year:04d}_{next_month:02d}"
    start = f"{next_year:04d}-{next_month:02d}-01"
    # 다음다음달 1일 (파티션 상한)
    if next_month == 12:
        end_year, end_month = next_year + 1, 1
    else:
        end_year, end_month = next_year, next_month + 1
    end = f"{end_year:04d}-{end_month:02d}-01"

    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (partition_name,)
    )
    if cur.fetchone() is None:
        cur.execute(
            f"CREATE TABLE {partition_name} PARTITION OF doc_chunks "
            f"FOR VALUES FROM (%s) TO (%s)",
            (start, end)
        )
        conn.commit()
        print(f"[partition] 파티션 생성: {partition_name} ({start} ~ {end})")


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
    parser.add_argument(
        "--extensions",
        help="rotate 대상 확장자 (쉼표/공백 구분, dot 없이. 예: md,log,txt). 미지정 시 projects.toml extensions → 기본값 폴백",
    )
    args = parser.parse_args()

    project = infer_project(explicit=args.project)
    if project not in PROJECTS:
        print(
            f"오류: 미등록 프로젝트 '{project}'. projects.toml 에 [projects.{project}] 블록을 추가하세요 (config.py 참조).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"프로젝트: {project}  (rotate 기준: {PROJECTS[project]['hot_days']}일 초과)")

    parsed = _parse_extensions(args.extensions)
    targets = discover_rotate_targets(project, extensions=parsed)
    done_targets = discover_done_rotate_targets(project, extensions=parsed)
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

        # dry-run: 제거 예정 빈 날짜폴더 출력
        docs_root = PROJECTS[project].get("docs_root")
        if docs_root:
            processed_dirs: set[Path] = set()
            for src, _ in targets:
                d = src.parent
                if docs_root in d.parents or d == docs_root:
                    processed_dirs.add(d)
            for folder in sorted(processed_dirs, key=lambda p: len(p.parts), reverse=True):
                if folder.exists() and _is_content_empty(folder):
                    print(f"[dry-run] 빈 폴더 제거 예정: {folder}")
        return

    # 실제 이동
    rotated = 0
    skipped = 0
    errors = 0

    with get_db_connection() as conn:
        ensure_next_month_partition(conn)
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

    # 회전 후 빈 날짜폴더 제거 (docs_root 하위만)
    docs_root = PROJECTS[project].get("docs_root")
    if docs_root:
        processed_dirs: set[Path] = set()
        for src, _ in targets:
            d = src.parent
            if docs_root in d.parents or d == docs_root:
                processed_dirs.add(d)
        for folder in sorted(processed_dirs, key=lambda p: len(p.parts), reverse=True):
            if folder.exists() and _is_content_empty(folder):
                for meta in list(folder.iterdir()):
                    meta.unlink()
                folder.rmdir()

    print(
        f"완료: 이동={rotated}개, 스킵(미임베딩)={skipped}개, 오류={errors}개"
    )


if __name__ == "__main__":
    main()

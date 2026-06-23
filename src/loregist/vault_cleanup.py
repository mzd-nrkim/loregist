"""
vault_cleanup.py — vault + cold 파일 정리 도구

사용법:
    python -m loregist.vault_cleanup --project <프로젝트명> [--dry-run | --apply]

동작:
    1. vault_cleanup opt-in 프로젝트에 한해 동작 (미opt-in이면 안내 후 종료)
    2. vault + cold 파일 목록과 doc_originals DB 대조
       - verify_in_db(): full_text 비어있지 않음 + file_hash 확인
    3. 삭제 후보 선정: DB 원문 존재(verify_in_db=True) + 보존 기간 초과 둘 다 만족
    4. --dry-run (기본): 삭제 후보 목록·경과일·DB 대조 결과만 출력, 실제 삭제 없음
    5. --apply 명시 시에만 실제 삭제 수행

안전장치 (이중):
    1. vault_cleanup opt-in (projects.toml의 vault_cleanup 키)
    2. --apply 명시 승인 (사용자 결정 필요, [U] 항목)

경과일 기준:
    파일 mtime (파일 수정 시각) 기준으로 경과일을 산출한다.
    파일명에 날짜가 있어도 mtime을 우선한다.
    (이유: mtime이 실제 파일 내용 변경 시점을 반영하며, 파일명 날짜는 없는 경우도 많음)
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from loregist.config import PROJECTS, VAULT_RETENTION_DAYS, DEFAULT_EXTENSIONS

try:
    import psycopg2
except ImportError:
    print("[ERROR] psycopg2가 설치되지 않았습니다.", file=sys.stderr)
    sys.exit(1)


def hash_file(path: Path) -> str:
    """파일의 SHA-256 해시를 반환한다."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_in_db(conn, project: str, path: Path) -> bool:
    """
    doc_originals에서 해당 파일의 원문이 저장되어 있는지 확인한다.

    조건:
      - full_text가 비어있지 않음 (None 또는 빈 문자열이 아님)
      - file_hash가 현재 파일의 SHA-256 해시와 일치

    반환: True = DB 원문 존재 + 해시 일치 / False = 미저장 또는 불일치
    """
    source_path = str(path)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT full_text, file_hash FROM doc_originals "
            "WHERE project = %s AND source_path = %s",
            (project, source_path),
        )
        row = cur.fetchone()

    if row is None:
        return False

    full_text, db_hash = row
    if not full_text:
        return False

    # 파일 해시 대조
    try:
        current_hash = hash_file(path)
    except OSError:
        return False

    return db_hash == current_hash


def _collect_vault_files(cfg: dict) -> list[Path]:
    """vault + cold 디렉터리에서 config extensions 기준 파일 목록을 수집한다."""
    files: list[Path] = []
    extensions = cfg.get("extensions", DEFAULT_EXTENSIONS[:])

    for dir_key in ("vault", "cold"):
        directory: "Path | None" = cfg.get(dir_key)
        if directory and directory.exists():
            for ext in extensions:
                files.extend(directory.rglob(f"*.{ext}"))

    # 중복 제거 (vault와 cold가 부모-자식 관계일 경우)
    return list({f.resolve(): f for f in files}.values())


def _elapsed_days(path: Path) -> float:
    """파일 mtime 기준 경과일을 반환한다."""
    mtime = path.stat().st_mtime
    now = datetime.now(tz=timezone.utc).timestamp()
    return (now - mtime) / 86400


def run(project: str, dry_run: bool = True) -> None:
    """
    vault 정리 메인 로직.

    Args:
        project: 프로젝트 키
        dry_run: True(기본) → 후보 목록만 출력, False → 실제 삭제
                 [U] --apply 명시 시에만 dry_run=False로 호출.
                 비가역 삭제이므로 사용자 명시 승인 없이 자동 실행 금지.
    """
    cfg = PROJECTS.get(project)
    if cfg is None:
        print(f"[ERROR] 프로젝트 '{project}'가 PROJECTS에 없습니다.", file=sys.stderr)
        sys.exit(1)

    vc = cfg.get("vault_cleanup", {})
    if not vc.get("active", False):
        print(
            f"[INFO] 프로젝트 '{project}'는 vault_cleanup opt-in이 설정되어 있지 않습니다.\n"
            f"  projects.toml의 [{project}] 블록에 'vault_cleanup = true' 또는 보존일(정수)를 추가하세요.",
            file=sys.stderr,
        )
        sys.exit(0)

    # retention_days=0 은 유효한 경계값(즉시 후보)이므로 None 여부로 분기.
    # `or VAULT_RETENTION_DAYS` 패턴은 0을 falsy로 취급해 fallback이 발생하므로 사용 금지.
    _rd = vc.get("retention_days")
    retention_days: int = VAULT_RETENTION_DAYS if _rd is None else _rd

    # vault + cold 파일 수집
    files = _collect_vault_files(cfg)

    if not files:
        print(f"[INFO] vault/cold 파일이 없습니다 (후보 0건, 에러 없이 종료)")
        return

    # DB 연결
    try:
        from loregist.config import get_db_connection
        conn_ctx = get_db_connection()
        conn = conn_ctx.__enter__()
    except Exception as e:
        print(f"[ERROR] DB 연결 실패: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        ok_count = 0
        not_saved_count = 0
        candidates: list[tuple[Path, float, bool]] = []  # (path, elapsed, in_db)

        for f in sorted(files):
            in_db = verify_in_db(conn, project, f)
            elapsed = _elapsed_days(f)

            if in_db:
                ok_count += 1
            else:
                not_saved_count += 1

            # 삭제 후보: DB 원문 존재 + 보존 기간 초과 둘 다 만족
            if in_db and elapsed >= retention_days:
                candidates.append((f, elapsed, in_db))

        print(f"\n[대조 결과] 총 {len(files)}건 — DB OK: {ok_count}건 / 미저장: {not_saved_count}건")
        print(f"[설정] 보존 기간: {retention_days}일 | 삭제 후보: {len(candidates)}건\n")

        if not candidates:
            print("[INFO] 삭제 후보가 없습니다.")
            return

        if dry_run:
            print("[DRY-RUN] 삭제 후보 목록 (실제 삭제 없음):")
            for path, elapsed, in_db in candidates:
                print(f"  {path}  ({elapsed:.1f}일 경과, DB={'OK' if in_db else 'MISSING'})")
            print(f"\n실제 삭제를 수행하려면 --apply 플래그를 추가하세요.")
        else:
            # [U] 비가역 삭제 실행 — --apply 명시 승인 조건:
            # 사용자가 dry-run 결과를 검토한 후 '--apply' 플래그를 명시적으로 지정한 경우에만 도달.
            # 이 코드 경로는 자동화 스크립트로 직접 호출하지 않는 것을 권장한다.
            deleted = 0
            errors = 0
            print("[APPLY] 실제 삭제 수행:")
            for path, elapsed, in_db in candidates:
                try:
                    path.unlink()
                    print(f"  [삭제] {path}  ({elapsed:.1f}일 경과)")
                    deleted += 1
                except OSError as e:
                    print(f"  [ERROR] {path} 삭제 실패: {e}", file=sys.stderr)
                    errors += 1
            print(f"\n[완료] 삭제: {deleted}건 / 실패: {errors}건")
            print("[NOTE] DB 원문(doc_originals.full_text)은 보존되어 있습니다 — 복원 가능.")
    finally:
        conn_ctx.__exit__(None, None, None)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="vault + cold 파일 정리 (opt-in 프로젝트 전용)"
    )
    parser.add_argument(
        "--project",
        required=True,
        help="대상 프로젝트 키 (vault_cleanup opt-in된 프로젝트만 유효)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="삭제 후보 목록만 출력, 실제 삭제 없음 (기본값)",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="실제 삭제 수행 (dry-run 검토 후 명시적 승인 시에만 사용)",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    run(args.project, dry_run=dry_run)


if __name__ == "__main__":
    main()

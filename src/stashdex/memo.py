#!/usr/bin/env python
"""stashdex memo — 메시지를 타임스탬프 파일명으로 vault/memo/ 에 저장."""
import argparse
import datetime
import os
import sys
from pathlib import Path

from stashdex.config import PROJECTS, infer_project


def run_memo(message: str, project: str | None = None) -> Path:
    """message를 <vault>/memo/<timestamp>_<ms>_<pid>.log 파일로 저장하고 경로를 반환한다."""
    resolved = infer_project(explicit=project)
    if resolved not in PROJECTS:
        print(
            f"오류: 미등록 프로젝트 '{resolved}'. projects.toml에 추가하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    vault = PROJECTS[resolved].get("vault")
    if vault is None:
        print(
            f"오류: 프로젝트 '{resolved}'에 vault 경로가 설정되지 않았습니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    memo_dir = Path(vault) / "memo"
    memo_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now()
    filename = f"{now:%Y%m%dT%H%M%S}_{now.microsecond // 1000:03d}_{os.getpid()}.log"
    memo_path = memo_dir / filename

    memo_path.write_text(message, encoding="utf-8")

    print(f"Saved to {memo_path}", file=sys.stderr)
    return memo_path


def main():
    parser = argparse.ArgumentParser(
        description="메시지를 타임스탬프 파일명으로 vault/memo/ 에 저장합니다.",
        usage="stashdex memo <메시지> [--project P]",
    )
    parser.add_argument("message", nargs="?", help="저장할 메시지")
    parser.add_argument("--project", help="프로젝트명 (기본: cwd 추론)")
    args = parser.parse_args()

    if not args.message:
        parser.print_usage(sys.stderr)
        print(
            "\n오류: 메시지를 입력하세요. 예: stashdex memo \"API 스펙 검토 완료\"",
            file=sys.stderr,
        )
        sys.exit(2)

    run_memo(args.message, project=args.project)


if __name__ == "__main__":
    main()

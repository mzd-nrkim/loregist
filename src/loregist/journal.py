#!/usr/bin/env python
"""loregist journal — 오늘 날짜 로그 파일에 [HH:MM] 메시지 append."""
import argparse
import datetime
import sys
from pathlib import Path

from loregist.config import PROJECTS, infer_project


def run_journal(message: str, project: str | None = None) -> Path:
    """message를 <vault>/journal/<today>.log 에 append하고 경로를 반환한다."""
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

    today = datetime.date.today().strftime("%Y-%m-%d")
    journal_dir = Path(vault) / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)

    log_path = journal_dir / f"{today}.log"
    timestamp = datetime.datetime.now().strftime("%H:%M")
    line = f"[{timestamp}] {message}\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)

    print(f"Appended to {log_path}", file=sys.stderr)
    return log_path


def main():
    parser = argparse.ArgumentParser(
        description="오늘 날짜 로그 파일에 메시지를 기록합니다.",
        usage="loregist journal <메시지> [--project P]",
    )
    parser.add_argument("message", nargs="?", help="기록할 메시지")
    parser.add_argument("--project", help="프로젝트명 (기본: cwd 추론)")
    args = parser.parse_args()

    if not args.message:
        parser.print_usage(sys.stderr)
        print(
            "\n오류: 메시지를 입력하세요. 예: loregist journal \"오늘 API 스펙 검토 완료\"",
            file=sys.stderr,
        )
        sys.exit(2)

    run_journal(args.message, project=args.project)


if __name__ == "__main__":
    main()

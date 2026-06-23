"""loregist project — project 서브커맨드 디스패처."""
import os
import sys


def _cmd_list() -> int:
    from loregist.config import dump_projects
    print(dump_projects(as_json=True))
    return 0


def _cmd_current() -> int:
    from loregist.config import infer_project
    cwd = os.environ.get("LOREGIST_CWD", os.getcwd())
    try:
        print(infer_project(cwd))
        return 0
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1


def _cmd_add(argv_after_subcommand: list) -> int:
    from loregist import onboard
    return onboard.main(argv_after_subcommand)


def main(argv: list | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        _print_usage()
        return 2

    subcmd = argv[0]
    rest = argv[1:]

    if subcmd == "list":
        return _cmd_list()
    elif subcmd == "current":
        return _cmd_current()
    elif subcmd == "add":
        return _cmd_add(rest)
    else:
        print(f"알 수 없는 서브커맨드: {subcmd}", file=sys.stderr)
        _print_usage()
        return 2


def _print_usage() -> None:
    print(
        "사용법: loregist project <list|current|add> [옵션]",
        file=sys.stderr,
    )
    print("  list     프로젝트 목록 JSON 출력", file=sys.stderr)
    print("  current  현재 디렉터리 기준 프로젝트 추론", file=sys.stderr)
    print("  add      새 프로젝트 온보딩 마법사 실행", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

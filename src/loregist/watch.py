#!/usr/bin/env python
"""loregist watch — 지정 디렉터리를 감시하여 config extensions 기반 확장자 변경 시 자동 embed."""
import argparse
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from loregist.config import PROJECTS, DEFAULT_EXTENSIONS, get_db_connection, infer_project
from loregist.embed import embed_file

class _EmbedHandler(FileSystemEventHandler):
    """파일 변경/생성 이벤트를 받아 embed_file()을 호출한다."""

    def __init__(self, project: str):
        super().__init__()
        self._project = project
        exts = PROJECTS[project].get("extensions", DEFAULT_EXTENSIONS[:])
        self._watched_suffixes = {"." + e.lstrip(".") for e in exts}

    def _is_target(self, path: str) -> bool:
        return Path(path).suffix in self._watched_suffixes

    def _handle(self, path: str) -> None:
        if not self._is_target(path):
            return
        try:
            with get_db_connection() as conn:
                embed_file(conn, self._project, path)
            print(f"[watch] embedded: {path}", flush=True)
        except Exception as e:
            print(f"[watch] 오류 ({path}): {e}", file=sys.stderr)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)


def _resolve_watch_dir(args_dir: str | None, project: str) -> Path:
    """
    --dir 미지정이면 현재 project의 vault 디렉터리를 반환한다.
    vault가 없으면 오류 후 종료.
    """
    if args_dir:
        return Path(args_dir).expanduser().resolve()

    vault = PROJECTS[project].get("vault")
    if vault is None:
        print(
            f"오류: 프로젝트 '{project}'에 vault 경로가 없습니다. --dir 로 디렉터리를 지정하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(vault)


def _validate_dir_in_project(watch_dir: Path, project: str, explicit_project: str | None) -> None:
    """
    watch_dir 이 project 범위(vault / docs_root / cold) 밖이면서
    --project 를 명시하지 않은 경우 오류 종료.
    """
    if explicit_project:
        return  # 명시적으로 지정됐으면 OK

    cfg = PROJECTS[project]
    project_roots = []
    for key in ("vault", "docs_root", "done", "cold"):
        val = cfg.get(key)
        if val:
            project_roots.append(Path(val))

    # handbook 경로 부모 디렉터리도 허용 범위에 추가
    for entry in cfg.get("handbook", []):
        p = entry["path"]
        if p.parent not in project_roots:
            project_roots.append(p.parent)

    for root in project_roots:
        try:
            watch_dir.relative_to(root)
            return  # 범위 안
        except ValueError:
            continue

    # 범위 밖 — 오류
    print(
        f"오류: '{watch_dir}'는 프로젝트 '{project}'의 범위 밖입니다.\n"
        f"  --project 옵션으로 프로젝트를 명시하거나, 프로젝트 vault/docs 하위 디렉터리를 지정하세요.",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="지정 디렉터리를 감시하여 config extensions 기반 확장자 변경 시 자동으로 embed합니다.",
        usage="loregist watch [--dir DIR] [--project P]",
    )
    parser.add_argument("--dir", help="감시할 디렉터리 (기본: 현재 프로젝트의 vault)")
    parser.add_argument("--project", help="프로젝트명 (기본: cwd 추론)")
    args = parser.parse_args()

    project = infer_project(explicit=args.project)
    if project not in PROJECTS:
        print(
            f"오류: 미등록 프로젝트 '{project}'. projects.toml에 추가하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    watch_dir = _resolve_watch_dir(args.dir, project)

    if not watch_dir.exists():
        watch_dir.mkdir(parents=True, exist_ok=True)

    _validate_dir_in_project(watch_dir, project, args.project)

    handler = _EmbedHandler(project=project)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=True)
    observer.start()
    print(f"[watch] 감시 시작: {watch_dir}  (Ctrl-C 로 종료)", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("Watch stopped.")

    observer.join()


if __name__ == "__main__":
    main()

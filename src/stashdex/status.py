#!/usr/bin/env python
"""stashdex status — 프로젝트별 임베딩 현황 대시보드."""
import argparse
import json
import sys

from stashdex.config import PROJECTS, get_db_connection
from stashdex import tui
from stashdex import drift as _drift


def run_status(conn, *, project_filter: "str | None" = None) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT project, COUNT(*) AS chunks, MAX(created_at) FROM doc_chunks GROUP BY project ORDER BY project"
    )
    rows = cur.fetchall()
    enabled = tui.color_enabled()
    print()
    for project, chunks, last_at in rows:
        if project_filter and project != project_filter:
            continue
        vault = PROJECTS.get(project, {}).get("vault", "-") if isinstance(PROJECTS.get(project), dict) else "-"
        date_str = last_at.strftime("%Y-%m-%d %H:%M") if last_at else "-"
        print(
            f"  {tui.c(project, 'bold', enabled=enabled)}"
            f"  {tui.c(str(chunks), 'cyan', enabled=enabled)} 청크"
            f"  {tui.c(date_str, 'dim', enabled=enabled)}"
        )
    if not rows:
        print(tui.c("  (임베딩된 문서 없음)", "yellow", enabled=enabled))
    print()

    # catalog 경고: catalog 경로가 설정됐으나 _wiki 디렉토리가 존재하지 않으면 경고
    warned = False
    for name, cfg in PROJECTS.items():
        if project_filter and name != project_filter:
            continue
        catalog_path = cfg.get("catalog")
        if catalog_path is not None and not catalog_path.exists():
            print(
                f"  {tui.c('⚠ _wiki 없음 → catalog-init 권장', 'yellow', enabled=enabled)}"
                f"  ({tui.c(name, 'bold', enabled=enabled)}: {catalog_path})"
            )
            warned = True
    if warned:
        print()

    # drift 섹션: catalog 대상 프로젝트 중 미반영 handbook이 있으면 표시
    drift_projects = [
        name for name, cfg in PROJECTS.items()
        if cfg.get("catalog") is not None
        and (project_filter is None or name == project_filter)
    ]
    for name in sorted(drift_projects):
        try:
            drifted = _drift.compute_drift(name)
        except Exception:
            continue
        if drifted:
            print(f"  ⚠️  {name}: 미반영 handbook {len(drifted)}개")
    if drift_projects:
        print()


def _build_json_output(conn, *, project_filter: "str | None" = None) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT project, COUNT(*) AS chunks, MAX(created_at) FROM doc_chunks GROUP BY project ORDER BY project"
    )
    rows = cur.fetchall()

    projects_info = []
    for project, chunks, last_at in rows:
        if project_filter and project != project_filter:
            continue
        projects_info.append({
            "project": project,
            "chunks": chunks,
            "last_at": last_at.isoformat() if last_at else None,
        })

    # drift 정보
    drift_map: dict[str, dict] = {}
    drift_projects = [
        name for name, cfg in PROJECTS.items()
        if cfg.get("catalog") is not None
        and (project_filter is None or name == project_filter)
    ]
    for name in drift_projects:
        try:
            summary = _drift.drift_summary(name)
            drift_map[name] = {"count": summary["count"], "files": summary["files"]}
        except Exception:
            drift_map[name] = {"count": 0, "files": []}

    return {
        "projects": projects_info,
        "drift": drift_map,
    }


def main():
    parser = argparse.ArgumentParser(description="stashdex status — 임베딩 현황 대시보드")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument("--project", default=None, help="특정 프로젝트만 표시")
    args = parser.parse_args()

    with get_db_connection() as conn:
        if args.json:
            output = _build_json_output(conn, project_filter=args.project)
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            run_status(conn, project_filter=args.project)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""loregist status — 프로젝트별 임베딩 현황 대시보드."""
from loregist.config import PROJECTS, get_db_connection
from loregist import tui


def run_status(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT project, COUNT(*) AS chunks, MAX(created_at) FROM doc_chunks GROUP BY project ORDER BY project"
    )
    rows = cur.fetchall()
    enabled = tui.color_enabled()
    print()
    for project, chunks, last_at in rows:
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


def main():
    with get_db_connection() as conn:
        run_status(conn)


if __name__ == "__main__":
    main()

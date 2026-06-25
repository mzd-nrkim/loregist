#!/usr/bin/env python
"""stashdex similar — 특정 파일과 유사한 과거 문서 찾기."""
import argparse
import sys
from pathlib import Path

from loregist.config import get_db_connection
from loregist.embed import load_embedder
from loregist.search import search_vector
from loregist import tui


def run_similar(path: str, top_k: int = 6) -> None:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        print(f"오류: 파일 없음 — {p}", file=sys.stderr)
        sys.exit(1)
    text = p.read_text(encoding="utf-8")
    model = load_embedder()
    vec = model.encode([f"query: {text[:2000]}"], show_progress_bar=False)[0].tolist()
    with get_db_connection() as conn:
        rows = search_vector(conn, project="", vector=vec, top_k=top_k + 1, all_projects=True)
    rows = [r for r in rows if Path(r["path"]).resolve() != p][:top_k]
    enabled = tui.color_enabled()
    if not rows:
        print(tui.c("유사 문서 없음", "yellow", enabled=enabled))
        return
    rendered, _ = tui.render_results(rows, query="", enabled=enabled)
    print(rendered)


def main():
    parser = argparse.ArgumentParser(description="유사 문서 찾기")
    parser.add_argument("path", help="기준 파일 경로")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    run_similar(args.path, top_k=args.top_k)


if __name__ == "__main__":
    main()

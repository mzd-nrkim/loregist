#!/usr/bin/env python
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from loregist.config import PROJECTS, get_db_connection, infer_project
from loregist.embed import load_embedder


def _rows_to_dicts(rows) -> list[dict]:
    return [
        {"project": r[0], "path": r[1], "kind": r[2], "score": float(r[3]), "text": r[4]}
        for r in rows
    ]


def embed_query(text: str) -> list[float]:
    model = load_embedder()
    vec = model.encode([f"query: {text}"], show_progress_bar=False)
    return vec[0].tolist()


def search_vector(conn, project: str, vector: list[float], top_k: int = 5, all_projects: bool = False, min_score: float | None = None) -> list[dict]:
    cur = conn.cursor()
    if all_projects:
        cur.execute(
            """
            SELECT project, source_path, source_kind,
                   1 - (embedding <=> %s::vector) AS score,
                   chunk_text
            FROM doc_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, vector, top_k),
        )
    else:
        cur.execute(
            """
            SELECT project, source_path, source_kind,
                   1 - (embedding <=> %s::vector) AS score,
                   chunk_text
            FROM doc_chunks
            WHERE project = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, project, vector, top_k),
        )
    rows = cur.fetchall()
    results = _rows_to_dicts(rows)
    if min_score is not None:
        results = [r for r in results if r["score"] >= min_score]
    return results


def search_fts(conn, project: str, query: str, top_k: int = 5, all_projects: bool = False) -> list[dict]:
    """bigm_similarity 기반 FTS. =% 연산자로 GIN 인덱스 활용, similarity_limit=0.0으로 단어 길이 무관하게 동작."""
    cur = conn.cursor()
    # similarity_limit를 0으로 설정해 짧은 쿼리도 =% 연산자로 필터링되지 않게 함
    cur.execute("SET LOCAL pg_bigm.similarity_limit = 0.0")
    if all_projects:
        cur.execute(
            """
            SELECT project, source_path, source_kind,
                   bigm_similarity(chunk_text, %s) AS score,
                   chunk_text
            FROM doc_chunks
            WHERE chunk_text =%% %s
            ORDER BY bigm_similarity(chunk_text, %s) DESC
            LIMIT %s
            """,
            (query, query, query, top_k),
        )
    else:
        cur.execute(
            """
            SELECT project, source_path, source_kind,
                   bigm_similarity(chunk_text, %s) AS score,
                   chunk_text
            FROM doc_chunks
            WHERE project = %s
              AND chunk_text =%% %s
            ORDER BY bigm_similarity(chunk_text, %s) DESC
            LIMIT %s
            """,
            (query, project, query, query, top_k),
        )
    rows = cur.fetchall()
    return _rows_to_dicts(rows)


def search_like(conn, project: str, query: str, top_k: int = 5, all_projects: bool = False) -> list[dict]:
    """LIKE %query% 패턴 검색."""
    pattern = f"%{query}%"
    cur = conn.cursor()
    if all_projects:
        cur.execute(
            """
            SELECT project, source_path, source_kind,
                   1.0 AS score,
                   chunk_text
            FROM doc_chunks
            WHERE chunk_text LIKE %s
            LIMIT %s
            """,
            (pattern, top_k),
        )
    else:
        cur.execute(
            """
            SELECT project, source_path, source_kind,
                   1.0 AS score,
                   chunk_text
            FROM doc_chunks
            WHERE project = %s
              AND chunk_text LIKE %s
            LIMIT %s
            """,
            (project, pattern, top_k),
        )
    rows = cur.fetchall()
    return _rows_to_dicts(rows)


def search_hybrid(conn, project: str, vector: list[float], query: str, top_k: int = 5, all_projects: bool = False, rrf_k: int = 60) -> list[dict]:
    """RRF hybrid: vector CTE + fts CTE FULL OUTER JOIN. rrf_k controls the RRF smoothing constant."""
    cur = conn.cursor()
    cur.execute("SET LOCAL pg_bigm.similarity_limit = 0.0")
    if all_projects:
        cur.execute(
            """
            WITH vec AS (
                SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                       ROW_NUMBER() OVER (ORDER BY c.embedding <=> %(qvec)s::vector) AS rnk
                FROM doc_chunks c
                ORDER BY c.embedding <=> %(qvec)s::vector
                LIMIT 50
            ),
            fts AS (
                SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                       ROW_NUMBER() OVER (ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC) AS rnk
                FROM doc_chunks c
                WHERE c.chunk_text =%% %(q)s
                ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC
                LIMIT 50
            )
            SELECT
                COALESCE(v.project, f.project) AS project,
                COALESCE(v.source_path, f.source_path) AS source_path,
                COALESCE(v.source_kind, f.source_kind) AS source_kind,
                COALESCE(1.0/(%(rrf_k)s + v.rnk), 0) + COALESCE(1.0/(%(rrf_k)s + f.rnk), 0) AS rrf_score,
                COALESCE(v.chunk_text, f.chunk_text) AS chunk_text
            FROM vec v
            FULL OUTER JOIN fts f ON v.id = f.id
            ORDER BY rrf_score DESC
            LIMIT %(top_k)s
            """,
            {"qvec": vector, "q": query, "top_k": top_k, "rrf_k": rrf_k},
        )
    else:
        cur.execute(
            """
            WITH vec AS (
                SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                       ROW_NUMBER() OVER (ORDER BY c.embedding <=> %(qvec)s::vector) AS rnk
                FROM doc_chunks c
                WHERE c.project = %(project)s
                ORDER BY c.embedding <=> %(qvec)s::vector
                LIMIT 50
            ),
            fts AS (
                SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                       ROW_NUMBER() OVER (ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC) AS rnk
                FROM doc_chunks c
                WHERE c.project = %(project)s
                  AND c.chunk_text =%% %(q)s
                ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC
                LIMIT 50
            )
            SELECT
                COALESCE(v.project, f.project) AS project,
                COALESCE(v.source_path, f.source_path) AS source_path,
                COALESCE(v.source_kind, f.source_kind) AS source_kind,
                COALESCE(1.0/(%(rrf_k)s + v.rnk), 0) + COALESCE(1.0/(%(rrf_k)s + f.rnk), 0) AS rrf_score,
                COALESCE(v.chunk_text, f.chunk_text) AS chunk_text
            FROM vec v
            FULL OUTER JOIN fts f ON v.id = f.id
            ORDER BY rrf_score DESC
            LIMIT %(top_k)s
            """,
            {"qvec": vector, "q": query, "top_k": top_k, "project": project, "rrf_k": rrf_k},
        )
    rows = cur.fetchall()
    return _rows_to_dicts(rows)


def run_search_staged(conn, mode: str, project: str, query: str, top_k: int = 5,
                      all_projects: bool = False, min_score: float | None = None,
                      rrf_k: int = 60, spinner=None) -> list[dict]:
    """단계별 스피너를 표시하며 검색을 수행한다. (TTY 경로 전용)
    spinner가 None이면 스피너 없이 run_search와 동일하게 동작.
    """
    if spinner is None:
        return run_search(conn, mode, project, query, top_k=top_k,
                          all_projects=all_projects, min_score=min_score, rrf_k=rrf_k)

    if mode in ("vector", "hybrid"):
        with spinner.step("모델 로딩"):
            model = load_embedder()
        with spinner.step("쿼리 임베딩"):
            vec = model.encode([f"query: {query}"], show_progress_bar=False)
            vector = vec[0].tolist()
        with spinner.step(f"검색({mode} 융합)" if mode == "hybrid" else "검색(vector)"):
            if mode == "vector":
                return search_vector(conn, project, vector, top_k=top_k,
                                     all_projects=all_projects, min_score=min_score)
            else:
                return search_hybrid(conn, project, vector, query, top_k=top_k,
                                     all_projects=all_projects, rrf_k=rrf_k)
    else:
        # fts / like: 단일 단계
        with spinner.step("검색"):
            return run_search(conn, mode, project, query, top_k=top_k,
                              all_projects=all_projects, min_score=min_score, rrf_k=rrf_k)


def _hit(rows: list[dict], expected_paths: list[str], top_k: int = 5) -> bool:
    """top-k 결과 중 path가 expected_paths 중 하나를 부분 포함하면 hit."""
    for row in rows[:top_k]:
        for expected in expected_paths:
            if expected in row["path"]:
                return True
    return False


def run_eval(conn, golden_path: str, rrf_k: int = 60) -> int:
    """골든 쿼리 평가 실행. 모드별(vector/fts/hybrid) 적중률과 hybrid의 rrf_k별 비교표를 출력한다."""
    with open(golden_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    queries = data.get("queries") or []
    if not queries:
        print("평가할 쿼리가 없습니다. golden-queries.yaml의 queries: 항목을 채워주세요.")
        return 0

    total = len(queries)
    modes = ["vector", "fts", "hybrid"]
    hits: dict[str, int] = {m: 0 for m in modes}
    failures: dict[str, list[str]] = {m: [] for m in modes}

    # rrf_k 순회용 hybrid 적중 수
    rrf_k_candidates = [10, 30, 60, 100]
    hybrid_hits_by_k: dict[int, int] = {k: 0 for k in rrf_k_candidates}

    valid_total = 0

    for item in queries:
        query = item["query"]
        project = item["project"]
        expected_paths = item.get("expected_paths", [])

        if project not in PROJECTS:
            print(f"  [SKIP] 미등록 프로젝트 '{project}' (query: {query!r})", file=sys.stderr)
            continue

        valid_total += 1
        vector = embed_query(query)

        # vector 모드
        rows_vec = search_vector(conn, project, vector, top_k=5)
        if _hit(rows_vec, expected_paths):
            hits["vector"] += 1
        else:
            failures["vector"].append(query)

        # fts 모드
        rows_fts = search_fts(conn, project, query, top_k=5)
        if _hit(rows_fts, expected_paths):
            hits["fts"] += 1
        else:
            failures["fts"].append(query)

        # hybrid 모드 (지정 rrf_k)
        rows_hybrid = search_hybrid(conn, project, vector, query, top_k=5, rrf_k=rrf_k)
        if _hit(rows_hybrid, expected_paths):
            hits["hybrid"] += 1
        else:
            failures["hybrid"].append(query)

        # rrf_k별 hybrid 적중
        for k in rrf_k_candidates:
            rows_k = search_hybrid(conn, project, vector, query, top_k=5, rrf_k=k)
            if _hit(rows_k, expected_paths):
                hybrid_hits_by_k[k] += 1

    if valid_total == 0:
        print("유효한 평가 쿼리가 없습니다.")
        return 0

    # 결과 표 출력
    print()
    print("=" * 52)
    print(f"  골든 쿼리 평가 결과  (총 {valid_total}개 쿼리)")
    print("=" * 52)
    print(f"  {'모드':<10} {'적중':>6} {'전체':>6} {'적중률':>8}")
    print("-" * 52)
    for mode in modes:
        h = hits[mode]
        pct = h / valid_total * 100
        print(f"  {mode:<10} {h:>6} {valid_total:>6} {pct:>7.1f}%")
    print("=" * 52)

    # 실패 쿼리 출력
    for mode in modes:
        if failures[mode]:
            print(f"\n[{mode}] 미적중 쿼리 ({len(failures[mode])}개):")
            for q in failures[mode]:
                print(f"  - {q!r}")

    # rrf_k별 hybrid 비교표
    print()
    print("=" * 52)
    print("  hybrid rrf_k별 적중률 비교")
    print("=" * 52)
    print(f"  {'rrf_k':<10} {'적중':>6} {'전체':>6} {'적중률':>8}")
    print("-" * 52)
    for k in rrf_k_candidates:
        h = hybrid_hits_by_k[k]
        pct = h / valid_total * 100
        marker = " <--" if k == rrf_k else ""
        print(f"  {k:<10} {h:>6} {valid_total:>6} {pct:>7.1f}%{marker}")
    print("=" * 52)

    return 0


def run_search(conn, mode: str, project: str, query: str, top_k: int = 5,
               all_projects: bool = False, min_score: float | None = None,
               rrf_k: int = 60) -> list[dict]:
    """mode에 따라 적절한 search_* 를 호출한다. (main/fallback 공용)"""
    if mode == "vector":
        vector = embed_query(query)
        return search_vector(conn, project, vector, top_k=top_k, all_projects=all_projects, min_score=min_score)
    elif mode == "fts":
        return search_fts(conn, project, query, top_k=top_k, all_projects=all_projects)
    elif mode == "like":
        return search_like(conn, project, query, top_k=top_k, all_projects=all_projects)
    elif mode == "hybrid":
        vector = embed_query(query)
        return search_hybrid(conn, project, vector, query, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
    raise ValueError(f"알 수 없는 모드: {mode}")


def fetch_context_chunks(conn, project: str, source_path: str, center_idx: int, window: int = 1) -> list[dict]:
    """매칭 청크의 앞뒤 이웃 청크를 DB에서 조회한다."""
    cur = conn.cursor()
    cur.execute(
        """SELECT chunk_index, chunk_text FROM doc_chunks
           WHERE project=%s AND source_path=%s
             AND chunk_index BETWEEN %s AND %s
             AND chunk_index != %s
           ORDER BY chunk_index""",
        (project, source_path, center_idx - window, center_idx + window, center_idx),
    )
    return [{"chunk_index": r[0], "text": r[1]} for r in cur.fetchall()]


def _recency_score(source_path: str) -> float:
    """파일 경로에서 날짜 패턴(YYYY-MM-DD)을 파싱해 recency score를 산출한다."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", source_path)
    if not m:
        return 0.0
    try:
        d = date.fromisoformat(m.group(1))
        days = (date.today() - d).days
        return 1.0 / (1.0 + max(0, days))
    except ValueError:
        return 0.0


def apply_recency_boost(rows: list[dict], boost: float) -> list[dict]:
    """recency_score * boost를 각 행의 score에 가산 후 재정렬."""
    if boost == 0.0:
        return rows
    for r in rows:
        r["score"] += _recency_score(r["path"]) * boost
    return sorted(rows, key=lambda r: r["score"], reverse=True)


def _history_path() -> Path:
    p = Path.home() / ".cache" / "loregist" / "history"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save_history(query: str) -> None:
    """쿼리를 이력 파일에 append. 500건 초과 시 앞줄 잘라냄."""
    try:
        p = _history_path()
        lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        lines.append(f"{datetime.now().isoformat()}\t{query}")
        if len(lines) > 500:
            lines = lines[-500:]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def load_history() -> None:
    """이력 파일을 readline에 로드해 ↑ 키로 재호출 가능하게 한다."""
    try:
        import readline
        p = _history_path()
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    readline.add_history(parts[1])
    except Exception:
        pass


def format_results(rows: list[dict]) -> str:
    if not rows:
        return "(결과 없음)"
    lines = []
    for r in rows:
        excerpt = r["text"].replace("\n", " ")[:100]
        lines.append(f"{r['project']} | {r['path'].split('/')[-1]} | {r['score']:.4f} | {excerpt}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="문서 검색 (vector/fts/like/hybrid)")
    parser.add_argument("query", nargs="?", help="검색어 (--eval 시 불필요)")
    parser.add_argument("--top-k", type=int, default=5, help="결과 수 (기본 5)")
    parser.add_argument("--project", help="프로젝트명 (기본: cwd 추론)")
    parser.add_argument("--all-projects", action="store_true", help="전체 프로젝트 검색")
    parser.add_argument("--min-score", type=float, default=None, help="최소 유사도 점수 컷오프 (예: 0.85, vector 모드에서만 적용)")
    parser.add_argument(
        "--mode",
        choices=["vector", "fts", "like", "hybrid"],
        default="hybrid",
        help="검색 모드: hybrid(기본, RRF 융합), vector(cosine 시맨틱), fts(bigm 유사도), like(LIKE 패턴)",
    )
    parser.add_argument("--eval", action="store_true", help="골든 쿼리 평가 모드 실행")
    parser.add_argument("--golden", default="golden-queries.yaml", help="골든 쿼리 YAML 경로 (기본: golden-queries.yaml)")
    parser.add_argument("--rrf-k", type=int, default=60, help="RRF 스무딩 상수 (기본 60, --eval 시 기준값으로도 사용)")
    parser.add_argument("--no-fallback", action="store_true", help="단일 프로젝트 0건이어도 전체 프로젝트 자동 재검색을 하지 않음")
    # 3-1: 신규 플래그
    parser.add_argument("--plain", action="store_true", help="TTY에서도 강제로 기존 한 줄 포맷 출력")
    parser.add_argument("--json", action="store_true", help="JSON 구조화 출력 (색상·인터랙션 off)")
    parser.add_argument("--open", type=int, default=None, metavar="N", dest="open_n",
                        help="N번 결과를 즉시 기본 앱으로 열고 종료 (루프 없음)")
    parser.add_argument("--no-interactive", action="store_true", help="카드만 출력, 오픈 프롬프트 생략")
    parser.add_argument("--no-context", action="store_true", help="매칭 청크 앞뒤 컨텍스트 청크 표시 비활성화")
    parser.add_argument("--recency-boost", type=float, default=0.0, metavar="BOOST",
                        help="날짜 기반 재랭킹 가중치 (기본 0.0=비활성화)")
    parser.add_argument("--no-history", action="store_true", help="검색 이력 저장·로드 비활성화")
    args = parser.parse_args()

    if args.eval:
        with get_db_connection() as conn:
            ret = run_eval(conn, args.golden, rrf_k=args.rrf_k)
        sys.exit(ret)

    if not args.query:
        parser.error("query 인자가 필요합니다. (--eval 없이 실행 시)")

    project = infer_project(explicit=args.project)
    if project not in PROJECTS:
        print(f"오류: 미등록 프로젝트 '{project}'. vector_config.py의 PROJECTS에 추가하세요.", file=sys.stderr)
        sys.exit(1)

    # 검색 이력 로드 (TTY + --no-history 아닐 때만)
    is_tty = sys.stdout.isatty()
    if is_tty and not args.no_history:
        load_history()

    # 3-3: 출력 모드 결정
    rich = is_tty and not args.plain and not args.json

    # 3-4: 헤더 — 비-rich는 기존 문구 그대로(테스트 보존), rich는 예쁜 헤더.
    #       단 --json은 stdout이 순수 JSON이어야 하므로 헤더를 찍지 않는다.
    if not rich and not args.json:
        print(f"검색 프로젝트: {project if not args.all_projects else '(전체)'}, 모드: {args.mode}")

    # 3-5: 검색 실행 (fallback 포함)
    with get_db_connection() as conn:
        if rich:
            from loregist import tui
            spinner = tui.Spinner(enabled=True)
            rows = run_search_staged(conn, args.mode, project, args.query, top_k=args.top_k,
                                     all_projects=args.all_projects, min_score=args.min_score,
                                     rrf_k=args.rrf_k, spinner=spinner)
        else:
            rows = run_search(conn, args.mode, project, args.query, top_k=args.top_k,
                              all_projects=args.all_projects, min_score=args.min_score, rrf_k=args.rrf_k)

        # fallback: 단일 스코프 0건 → 전체 프로젝트 자동 재검색
        if not rows and not args.all_projects and not args.no_fallback:
            print(f"[fallback] '{project}' 스코프 0건 → 전체 프로젝트 재검색 (끄려면 --no-fallback)", file=sys.stderr)
            if rich:
                rows = run_search_staged(conn, args.mode, project, args.query, top_k=args.top_k,
                                         all_projects=True, min_score=args.min_score,
                                         rrf_k=args.rrf_k, spinner=spinner)
            else:
                rows = run_search(conn, args.mode, project, args.query, top_k=args.top_k,
                                  all_projects=True, min_score=args.min_score, rrf_k=args.rrf_k)
            if rows:
                if not rich and not args.json:
                    print(f"검색 프로젝트: (전체, fallback), 모드: {args.mode}")

        # recency boost 적용
        if args.recency_boost != 0.0:
            rows = apply_recency_boost(rows, args.recency_boost)

        # 검색 이력 저장 (TTY + --no-history 아닐 때만)
        if is_tty and not args.no_history and args.query:
            save_history(args.query)

        # 3-6: --json 출력
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return

        # 3-7: 결과 렌더
        if rich:
            from loregist import tui
            # 컨텍스트 청크 수집 (--no-context 아닐 때)
            context_chunks = None
            if not args.no_context and rows:
                from loregist.tui import _group_by_doc
                grouped_for_ctx = _group_by_doc(rows)
                context_chunks = {}
                for g in grouped_for_ctx:
                    center_idx = g.get("chunk_index", 0)
                    ctx = fetch_context_chunks(conn, g["project"], g["path"], center_idx)
                    if ctx:
                        context_chunks[(g["project"], g["path"])] = ctx
            rendered, grouped = tui.render_results(rows, args.query, enabled=True, context_chunks=context_chunks)
            print(rendered)
        else:
            print(format_results(rows))
            grouped = None

        if not rows and args.mode == "vector":
            print("힌트: 약어·정확 키워드는 `--mode fts` 또는 `--mode hybrid`를 권장합니다.", file=sys.stderr)

        # 3-8: 오픈 처리
        if args.open_n is not None:
            # --open N: N번 즉시 열고 종료 (루프 없음)
            if rich and grouped:
                from loregist import tui
                idx = args.open_n - 1
                if 0 <= idx < len(grouped):
                    ok, msg = tui.open_path(grouped[idx]["path"])
                    if not ok:
                        ok, msg = tui.open_fulltext_fallback(conn, grouped[idx]["project"], grouped[idx]["path"])
                    if not ok:
                        print(f"열기 실패: {msg}", file=sys.stderr)
                else:
                    print(f"범위 오류: {args.open_n}번 결과가 없습니다.", file=sys.stderr)
            elif rows:
                # non-rich 모드에서도 --open 지원
                from loregist import tui as _tui
                grp = _tui._group_by_doc(rows)
                idx = args.open_n - 1
                if 0 <= idx < len(grp):
                    ok, msg = _tui.open_path(grp[idx]["path"])
                    if not ok:
                        ok, msg = _tui.open_fulltext_fallback(conn, grp[idx]["project"], grp[idx]["path"])
                    if not ok:
                        print(f"열기 실패: {msg}", file=sys.stderr)
                else:
                    print(f"범위 오류: {args.open_n}번 결과가 없습니다.", file=sys.stderr)
        elif rich and grouped and not args.no_interactive and sys.stdin.isatty():
            from loregist import tui
            tui.prompt_open(grouped, conn)


if __name__ == "__main__":
    main()

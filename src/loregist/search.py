#!/usr/bin/env python
import argparse
import json
import re
import sys
import calendar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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


def search_vector(conn, project: str, vector: list[float], top_k: int = 5, all_projects: bool = False, min_score: float | None = None, source_kinds: list[str] | None = None, created_at_since: "datetime | None" = None) -> list[dict]:
    cur = conn.cursor()
    source_filter_sql = "AND source_kind = ANY(%s)" if source_kinds is not None else ""
    since_filter_sql = "AND created_at >= %s" if created_at_since is not None else ""
    if all_projects:
        extra_params = []
        if source_kinds is not None:
            extra_params.append(source_kinds)
        if created_at_since is not None:
            extra_params.append(created_at_since)
        cur.execute(
            f"""
            SELECT project, source_path, source_kind,
                   1 - (embedding <=> %s::vector) AS score,
                   chunk_text
            FROM doc_chunks
            WHERE 1=1
              {source_filter_sql}
              {since_filter_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            [vector] + extra_params + [vector, top_k],
        )
    else:
        extra_params = []
        if source_kinds is not None:
            extra_params.append(source_kinds)
        if created_at_since is not None:
            extra_params.append(created_at_since)
        cur.execute(
            f"""
            SELECT project, source_path, source_kind,
                   1 - (embedding <=> %s::vector) AS score,
                   chunk_text
            FROM doc_chunks
            WHERE project = %s
              {source_filter_sql}
              {since_filter_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            [vector, project] + extra_params + [vector, top_k],
        )
    rows = cur.fetchall()
    results = _rows_to_dicts(rows)
    if min_score is not None:
        results = [r for r in results if r["score"] >= min_score]
    return results


def search_fts(conn, project: str, query: str, top_k: int = 5, all_projects: bool = False, source_kinds: list[str] | None = None, created_at_since: "datetime | None" = None) -> list[dict]:
    """bigm_similarity 기반 FTS. =% 연산자로 GIN 인덱스 활용, similarity_limit=0.0으로 단어 길이 무관하게 동작."""
    cur = conn.cursor()
    # similarity_limit를 0으로 설정해 짧은 쿼리도 =% 연산자로 필터링되지 않게 함
    cur.execute("SET LOCAL pg_bigm.similarity_limit = 0.0")
    source_filter_sql = "AND source_kind = ANY(%s)" if source_kinds is not None else ""
    since_filter_sql = "AND created_at >= %s" if created_at_since is not None else ""
    if all_projects:
        extra_params: list = []
        if source_kinds is not None:
            extra_params.append(source_kinds)
        if created_at_since is not None:
            extra_params.append(created_at_since)
        cur.execute(
            f"""
            SELECT project, source_path, source_kind,
                   bigm_similarity(chunk_text, %s) AS score,
                   chunk_text
            FROM doc_chunks
            WHERE chunk_text =%% %s
              {source_filter_sql}
              {since_filter_sql}
            ORDER BY bigm_similarity(chunk_text, %s) DESC
            LIMIT %s
            """,
            [query, query] + extra_params + [query, top_k],
        )
    else:
        extra_params = []
        if source_kinds is not None:
            extra_params.append(source_kinds)
        if created_at_since is not None:
            extra_params.append(created_at_since)
        cur.execute(
            f"""
            SELECT project, source_path, source_kind,
                   bigm_similarity(chunk_text, %s) AS score,
                   chunk_text
            FROM doc_chunks
            WHERE project = %s
              AND chunk_text =%% %s
              {source_filter_sql}
              {since_filter_sql}
            ORDER BY bigm_similarity(chunk_text, %s) DESC
            LIMIT %s
            """,
            [query, project, query] + extra_params + [query, top_k],
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


def search_hybrid(conn, project: str, vector: list[float], query: str, top_k: int = 5, all_projects: bool = False, rrf_k: int = 60, source_kinds: list[str] | None = None, created_at_since: "datetime | None" = None) -> list[dict]:
    """RRF hybrid: vector CTE + fts CTE FULL OUTER JOIN. rrf_k controls the RRF smoothing constant."""
    cur = conn.cursor()
    cur.execute("SET LOCAL pg_bigm.similarity_limit = 0.0")
    source_filter_sql = "AND c.source_kind = ANY(%(source_kinds)s)" if source_kinds is not None else ""
    since_filter_sql = "AND c.created_at >= %(created_at_since)s" if created_at_since is not None else ""
    if all_projects:
        params: dict = {"qvec": vector, "q": query, "top_k": top_k, "rrf_k": rrf_k}
        if source_kinds is not None:
            params["source_kinds"] = source_kinds
        if created_at_since is not None:
            params["created_at_since"] = created_at_since
        cur.execute(
            f"""
            WITH vec AS (
                SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                       ROW_NUMBER() OVER (ORDER BY c.embedding <=> %(qvec)s::vector) AS rnk
                FROM doc_chunks c
                WHERE 1=1
                  {source_filter_sql}
                  {since_filter_sql}
                ORDER BY c.embedding <=> %(qvec)s::vector
                LIMIT 50
            ),
            fts AS (
                SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                       ROW_NUMBER() OVER (ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC) AS rnk
                FROM doc_chunks c
                WHERE c.chunk_text =%% %(q)s
                  {source_filter_sql}
                  {since_filter_sql}
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
            params,
        )
    else:
        params = {"qvec": vector, "q": query, "top_k": top_k, "project": project, "rrf_k": rrf_k}
        if source_kinds is not None:
            params["source_kinds"] = source_kinds
        if created_at_since is not None:
            params["created_at_since"] = created_at_since
        cur.execute(
            f"""
            WITH vec AS (
                SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                       ROW_NUMBER() OVER (ORDER BY c.embedding <=> %(qvec)s::vector) AS rnk
                FROM doc_chunks c
                WHERE c.project = %(project)s
                  {source_filter_sql}
                  {since_filter_sql}
                ORDER BY c.embedding <=> %(qvec)s::vector
                LIMIT 50
            ),
            fts AS (
                SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                       ROW_NUMBER() OVER (ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC) AS rnk
                FROM doc_chunks c
                WHERE c.project = %(project)s
                  AND c.chunk_text =%% %(q)s
                  {source_filter_sql}
                  {since_filter_sql}
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
            params,
        )
    rows = cur.fetchall()
    return _rows_to_dicts(rows)


def get_active_partitions(conn, since: datetime) -> list[str]:
    """created_at 범위가 since 이후인 월별 파티션 이름 목록을 반환한다."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name ~ '^doc_chunks_[0-9]{4}_[0-9]{2}$'
        ORDER BY table_name
        """
    )
    rows = cur.fetchall()
    result = []
    for (name,) in rows:
        # doc_chunks_YYYY_MM 형태에서 연월 파싱
        parts = name.split('_')  # ['doc', 'chunks', 'YYYY', 'MM']
        try:
            year, month = int(parts[2]), int(parts[3])
            partition_start = datetime(year, month, 1, tzinfo=since.tzinfo)
            # 파티션 범위 [start, end]가 [since, ∞)와 겹치면 포함
            last_day = calendar.monthrange(year, month)[1]
            partition_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=since.tzinfo)
            if partition_end >= since:
                result.append(name)
        except (IndexError, ValueError):
            continue
    return result


def search_multistep(
    conn,
    project: str,
    vector: list[float],
    query: str,
    tiers: list[str] | None = None,
    threshold: float = 0.80,
    top_k: int = 5,
    mode: str = "hybrid",
    all_projects: bool = False,
    rrf_k: int = 60,
) -> list[dict]:
    """tier 단계별로 검색 범위를 확장해 threshold를 충족하는 결과를 반환한다.

    tiers: ["m1","m3","m6","m12"] 또는 ["auto"] (auto는 m1→m3→m6→m12 순 확장)
    threshold: top-1 score가 이 값 이상이면 즉시 반환
    """
    TIER_DAYS = {"m1": 30, "m3": 90, "m6": 180, "m12": 365, "all": None}
    ALL_TIERS = ["m1", "m3", "m6", "m12", "all"]

    if tiers is None or tiers == ["auto"] or "auto" in tiers:
        tier_sequence = ALL_TIERS
    else:
        tier_sequence = [t for t in ALL_TIERS if t in tiers]

    def _search_vector_since(since: "datetime | None") -> list[dict]:
        cur = conn.cursor()
        since_sql = "AND created_at >= %s" if since is not None else ""
        if all_projects:
            extra: list = [since] if since is not None else []
            cur.execute(
                f"""
                SELECT project, source_path, source_kind,
                       1 - (embedding <=> %s::vector) AS score,
                       chunk_text
                FROM doc_chunks
                WHERE 1=1
                  {since_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                [vector] + extra + [vector, top_k],
            )
        else:
            extra = [since] if since is not None else []
            cur.execute(
                f"""
                SELECT project, source_path, source_kind,
                       1 - (embedding <=> %s::vector) AS score,
                       chunk_text
                FROM doc_chunks
                WHERE project = %s
                  {since_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                [vector, project] + extra + [vector, top_k],
            )
        return _rows_to_dicts(cur.fetchall())

    def _search_hybrid_since(since: "datetime | None") -> list[dict]:
        cur = conn.cursor()
        cur.execute("SET LOCAL pg_bigm.similarity_limit = 0.0")
        since_sql = "AND c.created_at >= %(since)s" if since is not None else ""
        if all_projects:
            p: dict = {"qvec": vector, "q": query, "top_k": top_k, "rrf_k": rrf_k}
            if since is not None:
                p["since"] = since
            cur.execute(
                f"""
                WITH vec AS (
                    SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                           ROW_NUMBER() OVER (ORDER BY c.embedding <=> %(qvec)s::vector) AS rnk
                    FROM doc_chunks c
                    WHERE 1=1
                      {since_sql}
                    ORDER BY c.embedding <=> %(qvec)s::vector
                    LIMIT 50
                ),
                fts AS (
                    SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                           ROW_NUMBER() OVER (ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC) AS rnk
                    FROM doc_chunks c
                    WHERE c.chunk_text =%% %(q)s
                      {since_sql}
                    ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC
                    LIMIT 50
                )
                SELECT
                    COALESCE(v.project, f.project),
                    COALESCE(v.source_path, f.source_path),
                    COALESCE(v.source_kind, f.source_kind),
                    COALESCE(1.0/(%(rrf_k)s + v.rnk), 0) + COALESCE(1.0/(%(rrf_k)s + f.rnk), 0),
                    COALESCE(v.chunk_text, f.chunk_text)
                FROM vec v
                FULL OUTER JOIN fts f ON v.id = f.id
                ORDER BY 4 DESC
                LIMIT %(top_k)s
                """,
                p,
            )
        else:
            p = {"qvec": vector, "q": query, "top_k": top_k, "project": project, "rrf_k": rrf_k}
            if since is not None:
                p["since"] = since
            cur.execute(
                f"""
                WITH vec AS (
                    SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                           ROW_NUMBER() OVER (ORDER BY c.embedding <=> %(qvec)s::vector) AS rnk
                    FROM doc_chunks c
                    WHERE c.project = %(project)s
                      {since_sql}
                    ORDER BY c.embedding <=> %(qvec)s::vector
                    LIMIT 50
                ),
                fts AS (
                    SELECT c.id, c.project, c.source_path, c.source_kind, c.chunk_text,
                           ROW_NUMBER() OVER (ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC) AS rnk
                    FROM doc_chunks c
                    WHERE c.project = %(project)s
                      AND c.chunk_text =%% %(q)s
                      {since_sql}
                    ORDER BY bigm_similarity(c.chunk_text, %(q)s) DESC
                    LIMIT 50
                )
                SELECT
                    COALESCE(v.project, f.project),
                    COALESCE(v.source_path, f.source_path),
                    COALESCE(v.source_kind, f.source_kind),
                    COALESCE(1.0/(%(rrf_k)s + v.rnk), 0) + COALESCE(1.0/(%(rrf_k)s + f.rnk), 0),
                    COALESCE(v.chunk_text, f.chunk_text)
                FROM vec v
                FULL OUTER JOIN fts f ON v.id = f.id
                ORDER BY 4 DESC
                LIMIT %(top_k)s
                """,
                p,
            )
        return _rows_to_dicts(cur.fetchall())

    last_results: list[dict] = []
    for tier in tier_sequence:
        if tier == "all":
            # since=None → 시간 제한 없이 전체 검색
            if mode == "vector":
                results = _search_vector_since(None)
            else:
                results = _search_hybrid_since(None)
            results = sorted(results, key=lambda r: r["score"], reverse=True)
            last_results = results
            if results and results[0]["score"] >= threshold:
                return results
            continue

        days = TIER_DAYS[tier]
        since = datetime.now(timezone.utc) - timedelta(days=days)
        partitions = get_active_partitions(conn, since)
        if not partitions:
            continue

        if mode == "vector":
            results = _search_vector_since(since)
        else:
            results = _search_hybrid_since(since)

        results = sorted(results, key=lambda r: r["score"], reverse=True)
        last_results = results

        if results and results[0]["score"] >= threshold:
            return results

    return last_results


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


# ─── Q-1-2~Q-1-4: wiki/hot/cold tier 검색 함수 ───────────────────────────────

def search_wiki(
    conn,
    project: str,
    vector: list[float],
    query: str,
    top_k: int = 5,
    all_projects: bool = False,
    rrf_k: int = 60,
) -> "tuple[list[dict], float]":
    """wiki(catalog/handbook) 청크만 hybrid 검색. 게이트용 cosine top-1 score도 반환."""
    results = search_hybrid(
        conn, project, vector, query,
        top_k=top_k, all_projects=all_projects, rrf_k=rrf_k,
        source_kinds=["catalog", "handbook"],
    )
    vec_results = search_vector(
        conn, project, vector,
        top_k=1, all_projects=all_projects,
        source_kinds=["catalog", "handbook"],
    )
    cosine_top1 = vec_results[0]["score"] if vec_results else 0.0
    return results, cosine_top1


def search_hot(
    conn,
    project: str,
    vector: list[float],
    query: str,
    hot_days: int,
    top_k: int = 5,
    all_projects: bool = False,
    rrf_k: int = 60,
) -> "tuple[list[dict], float]":
    """최근 hot_days 이내 md/log 청크 hybrid 검색. 게이트용 cosine top-1 score도 반환."""
    since = datetime.now(timezone.utc) - timedelta(days=hot_days)
    results = search_hybrid(
        conn, project, vector, query,
        top_k=top_k, all_projects=all_projects, rrf_k=rrf_k,
        source_kinds=["md", "log"],
        created_at_since=since,
    )
    vec_results = search_vector(
        conn, project, vector,
        top_k=1, all_projects=all_projects,
        source_kinds=["md", "log"],
        created_at_since=since,
    )
    cosine_top1 = vec_results[0]["score"] if vec_results else 0.0
    return results, cosine_top1


def search_cold_raw(
    conn,
    project: str,
    vector: list[float],
    query: str,
    threshold: float = 0.80,
    top_k: int = 5,
    all_projects: bool = False,
    rrf_k: int = 60,
) -> list[dict]:
    """search_multistep 재사용 — m1~m12~all tier 순차 확장."""
    return search_multistep(
        conn,
        project=project,
        vector=vector,
        query=query,
        tiers=["auto"],
        threshold=threshold,
        top_k=top_k,
        mode="hybrid",
        all_projects=all_projects,
        rrf_k=rrf_k,
    )


# ─── Q-2-1: 파일 검색 폴더 수집 ───────────────────────────────────────────────

def get_search_file_folders(project: str) -> list[str]:
    """프로젝트 설정에서 agentic 파일 검색 대상 폴더 목록을 반환한다."""
    import datetime as _dt
    cfg = PROJECTS.get(project, {})
    folders: list[str] = []
    seen: set[str] = set()

    def _add(p: "Path | str | None") -> None:
        if p is None:
            return
        s = str(p)
        if s not in seen and Path(s).exists():
            seen.add(s)
            folders.append(s)

    # catalog 경로
    catalog = cfg.get("catalog")
    if catalog is not None:
        _add(catalog)

    # handbook 파일들의 부모 디렉터리
    for entry in cfg.get("handbook", []):
        parent = Path(str(entry["path"])).parent
        _add(parent)

    # docs_root 아래 날짜 폴더 (hot_days 이내, _wiki 제외)
    docs_root = cfg.get("docs_root")
    hot_days = cfg.get("hot_days", 7)
    if docs_root is not None:
        today = _dt.date.today()
        for child in Path(str(docs_root)).iterdir():
            if child.name == "_wiki":
                continue
            if not child.is_dir():
                continue
            try:
                folder_date = _dt.date.fromisoformat(child.name)
                if (today - folder_date).days <= hot_days:
                    _add(child)
            except ValueError:
                pass

    return folders


# ─── Q-2-3: agentic 파일 검색 ─────────────────────────────────────────────────

def search_files_agentic(query: str, project: str) -> list[dict]:
    """파일 기반 agentic 검색. claude subprocess를 기동해 폴더에서 관련 내용을 찾는다."""
    import subprocess
    import os
    from loregist import auto_update

    folders = get_search_file_folders(project)
    if not folders:
        return []

    argv = auto_update.build_search_command(query, folders)
    child_env = os.environ.copy()
    child_env["LOREGIST_AUTO_GUARD"] = "1"
    try:
        proc = subprocess.run(argv, env=child_env, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, OSError):
        return []
    except subprocess.TimeoutExpired:
        return []
    if proc.returncode != 0:
        return []

    report = auto_update.parse_report(proc.stdout)
    summary = report.get("summary", "")
    # summary에서 JSON 리스트 파싱 시도
    try:
        import json as _json
        raw_list = _json.loads(summary)
        if not isinstance(raw_list, list):
            return []
    except (ValueError, TypeError):
        return []

    results: list[dict] = []
    for r in raw_list:
        if not isinstance(r, dict):
            continue
        results.append({
            "path": r.get("source_path", ""),
            "score": float(r.get("score", 0.0)),
            "text": r.get("chunk_text", ""),
            "kind": "file",
            "project": project,
            "confidence": float(r.get("confidence", 0.0)),
        })
    return results


# ─── Q-3-6: 헬퍼 함수 ─────────────────────────────────────────────────────────

def _merge_dedup(base: list[dict], new: list[dict]) -> list[dict]:
    """path 기준 dedup. 동일 path면 최고 score 행 보존."""
    seen = {r["path"]: r for r in base}
    for r in new:
        p = r["path"]
        if p not in seen or r["score"] > seen[p]["score"]:
            seen[p] = r
    return list(seen.values())


def _sort_results(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: r["score"], reverse=True)


# ─── Q-3: 오케스트레이터 ───────────────────────────────────────────────────────

def search_tiered(
    conn,
    project: str,
    query: str,
    *,
    strategy: str = "single",
    threshold: float = 0.80,
    top_k: int = 5,
    recency_boost: bool = False,
    all_projects: bool = False,
    rrf_k: int = 60,
    wiki_boost: float = 1.0,
    rich: bool = False,
) -> list[dict]:
    """wiki우선 cascade 다단계검색 오케스트레이터."""
    import concurrent.futures

    # Q-3-1: single strategy
    if strategy == "single":
        return run_search(conn, "hybrid", project, query, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)

    # Q-3-2: cascade strategy
    if strategy == "cascade":
        vector = embed_query(query)
        tier_order = ["hot", "wiki"] if recency_boost else ["wiki", "hot"]
        results: list[dict] = []
        for tier_name in tier_order:
            if tier_name == "wiki":
                tier_results, cosine = search_wiki(conn, project, vector, query, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
            else:
                hot_days = PROJECTS.get(project, {}).get("hot_days", 7) if not all_projects else 7
                tier_results, cosine = search_hot(conn, project, vector, query, hot_days=hot_days, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
            results = _merge_dedup(results, tier_results)
            if cosine >= threshold:
                return _sort_results(results)
        # tier 3 - cold raw
        cold_results = search_cold_raw(conn, project, vector, query, threshold=threshold, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
        results = _merge_dedup(results, cold_results)
        return _sort_results(results)

    # Q-3-3: fusion strategy
    if strategy == "fusion":
        vector = embed_query(query)
        wiki_results, _ = search_wiki(conn, project, vector, query, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
        hot_days = PROJECTS[project]["hot_days"] if not all_projects else 7
        hot_results, _ = search_hot(conn, project, vector, query, hot_days=hot_days, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
        cold_results = search_cold_raw(conn, project, vector, query, threshold=threshold, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
        file_results = search_files_agentic(query, project)
        if wiki_boost != 1.0:
            for r in wiki_results + hot_results:
                r["score"] *= wiki_boost
        all_res = _merge_dedup(wiki_results, hot_results)
        all_res = _merge_dedup(all_res, cold_results)
        all_res = _merge_dedup(all_res, file_results)
        return _sort_results(all_res)[:top_k]

    # Q-3-4: speculative strategy
    if strategy == "speculative":
        vector = embed_query(query)
        # 파일검색 백그라운드 발사
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        file_future = executor.submit(search_files_agentic, query, project)

        # DB tier cascade 진행
        all_res_spec: list[dict] = []
        tier_order_spec = ["hot", "wiki"] if recency_boost else ["wiki", "hot"]
        early_exit = False
        for tier_name in tier_order_spec:
            if tier_name == "wiki":
                tier_results, cosine = search_wiki(conn, project, vector, query, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
            else:
                hot_days = PROJECTS.get(project, {}).get("hot_days", 7) if not all_projects else 7
                tier_results, cosine = search_hot(conn, project, vector, query, hot_days=hot_days, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
            all_res_spec = _merge_dedup(all_res_spec, tier_results)
            if cosine >= threshold:
                early_exit = True
                break
        if not early_exit:
            cold_results = search_cold_raw(conn, project, vector, query, threshold=threshold, top_k=top_k, all_projects=all_projects, rrf_k=rrf_k)
            all_res_spec = _merge_dedup(all_res_spec, cold_results)

        # 파일 future 대기
        try:
            file_results = file_future.result(timeout=130)
            all_res_spec = _merge_dedup(all_res_spec, file_results)
        except (concurrent.futures.TimeoutError, Exception):
            pass
        finally:
            executor.shutdown(wait=False)

        return _sort_results(all_res_spec)[:top_k]

    raise ValueError(f"알 수 없는 strategy: {strategy}")


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
    parser.add_argument(
        "--tier",
        choices=["m1", "m3", "m6", "m12", "auto"],
        default=None,
        help="멀티스텝 검색 tier (m1=30일, m3=90일, m6=180일, m12=365일, auto=단계적 확장). 미지정 시 전체 테이블 검색(기존 동작 유지)",
    )
    parser.add_argument(
        "--tier-threshold",
        type=float,
        default=0.80,
        help="멀티스텝 검색 확장 임계치 (기본 0.80, top-1 스코어가 이 값 미만이면 다음 tier로 확장)",
    )
    parser.add_argument(
        "--strategy",
        choices=["single", "cascade", "fusion", "speculative"],
        default="single",
        help="다단계 검색 전략 (기본: single=현행 단일 hybrid)",
    )
    parser.add_argument(
        "--cascade-threshold",
        type=float,
        default=0.80,
        help="cascade/speculative 종료 cosine 임계치 (기본 0.80)",
    )
    parser.add_argument(
        "--wiki-boost",
        type=float,
        default=1.0,
        help="fusion 전략에서 wiki/hot 청크 score 배율 (기본 1.0)",
    )
    args = parser.parse_args()

    if args.eval:
        from loregist.search_eval import run_eval
        with get_db_connection() as conn:
            ret = run_eval(conn, args.golden, rrf_k=args.rrf_k)
        sys.exit(ret)

    if not args.query:
        parser.error("query 인자가 필요합니다. (--eval 없이 실행 시)")

    project = infer_project(explicit=args.project)
    if project not in PROJECTS:
        print(f"오류: 미등록 프로젝트 '{project}'. projects.toml에 추가하세요.", file=sys.stderr)
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
        if args.tier is not None:
            # 멀티스텝 tier 검색 경로
            vector = embed_query(args.query)
            tier_list = ["auto"] if args.tier == "auto" else [args.tier]
            rows = search_multistep(
                conn,
                project=project,
                vector=vector,
                query=args.query,
                tiers=tier_list,
                threshold=args.tier_threshold,
                top_k=args.top_k,
                mode=args.mode,
                all_projects=args.all_projects,
                rrf_k=args.rrf_k,
            )
        elif args.strategy != "single":
            rows = search_tiered(
                conn,
                project=project,
                query=args.query,
                strategy=args.strategy,
                threshold=args.cascade_threshold,
                top_k=args.top_k,
                recency_boost=(args.recency_boost != 0.0),
                all_projects=args.all_projects,
                rrf_k=args.rrf_k,
                wiki_boost=args.wiki_boost,
                rich=rich,
            )
        elif rich:
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

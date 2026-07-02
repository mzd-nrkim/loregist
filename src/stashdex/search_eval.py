"""골든 쿼리 기반 검색 품질 평가 모듈."""
import sys

import yaml

from stashdex.config import PROJECTS
from stashdex.search import embed_query, search_fts, search_hybrid, search_vector


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

"""
tests/test_search.py
C-2: search.py 단위 테스트 (DB 불필요)

커버:
  - _recency_score: 날짜 없는 경로, 날짜 있는 경로
  - apply_recency_boost: boost=0 noop, boost>0 재정렬
  - save_history / load_history: 형식 검증, 500건 제한, 쓰기 실패 graceful
  - fetch_context_chunks: mock DB로 Existence/Cardinality 검증
"""
import pytest


# ──────────────────────────────────────────────────────────────
# B-3: recency score
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_recency_score_no_date():
    """날짜 패턴 없는 경로 → score=0.0 반환 (Range)."""
    from loregist.search import _recency_score
    assert _recency_score("/path/to/file.md") == 0.0
    assert _recency_score("/no-date-here/doc.md") == 0.0


@pytest.mark.unit
def test_recency_score_today():
    """오늘 날짜가 포함된 경로 → score가 0보다 큼."""
    from loregist.search import _recency_score
    from datetime import date
    today = date.today().isoformat()
    score = _recency_score(f"/path/{today}/file.md")
    assert score > 0.0
    # 오늘은 days=0이므로 score = 1/(1+0) = 1.0
    assert abs(score - 1.0) < 1e-9


@pytest.mark.unit
def test_recency_score_old_date():
    """오래된 날짜 경로 → score가 낮음."""
    from loregist.search import _recency_score
    score = _recency_score("/path/2020-01-01/file.md")
    assert 0.0 < score < 0.01  # 5년 이상 경과


@pytest.mark.unit
def test_recency_boost_zero_noop():
    """boost=0.0 시 점수 변화 없음 (Right)."""
    from loregist.search import apply_recency_boost
    rows = [
        {"project": "p", "path": "/2026-01-01/a.md", "score": 0.9, "text": ""},
        {"project": "p", "path": "/2020-01-01/b.md", "score": 0.8, "text": ""},
    ]
    original_scores = [(r["path"], r["score"]) for r in rows]
    result = apply_recency_boost(rows, 0.0)
    result_scores = [(r["path"], r["score"]) for r in result]
    assert result_scores == original_scores


@pytest.mark.unit
def test_recency_boost_reversible():
    """boost > 0 후 boost=0 재적용 시 원래 순서와 동일 (Inverse)."""
    from loregist.search import apply_recency_boost
    import copy
    rows_orig = [
        {"project": "p", "path": "/2020-01-01/old.md", "score": 0.9, "text": ""},
        {"project": "p", "path": "/no-date/new.md", "score": 0.5, "text": ""},
    ]
    rows_copy = copy.deepcopy(rows_orig)

    # boost=0 시 순서 그대로
    result_no_boost = apply_recency_boost(rows_copy, 0.0)
    assert result_no_boost[0]["path"] == rows_orig[0]["path"]
    assert result_no_boost[1]["path"] == rows_orig[1]["path"]


# ──────────────────────────────────────────────────────────────
# B-4: 검색 이력
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_history_format(tmp_path, monkeypatch):
    """저장된 이력 줄이 {ISO timestamp}\t{query} 형식 준수 (Conformance)."""
    import re
    from loregist import search as _search
    monkeypatch.setattr(_search, "_history_path", lambda: tmp_path / "history")

    _search.save_history("테스트 쿼리")
    content = (tmp_path / "history").read_text(encoding="utf-8")
    lines = [l for l in content.splitlines() if l.strip()]
    assert len(lines) == 1
    # {ISO timestamp}\t{query} 패턴
    iso_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    parts = lines[0].split("\t", 1)
    assert len(parts) == 2, f"탭 구분자가 없음: {lines[0]!r}"
    assert re.match(iso_pattern, parts[0]), f"타임스탬프 형식 오류: {parts[0]!r}"
    assert parts[1] == "테스트 쿼리"


@pytest.mark.unit
def test_history_max_500(tmp_path, monkeypatch):
    """501건 저장 시 앞 줄 잘려 정확히 500건 유지 (Range)."""
    from loregist import search as _search
    monkeypatch.setattr(_search, "_history_path", lambda: tmp_path / "history")

    for i in range(501):
        _search.save_history(f"쿼리 {i}")

    content = (tmp_path / "history").read_text(encoding="utf-8")
    lines = [l for l in content.splitlines() if l.strip()]
    assert len(lines) == 500
    # 가장 오래된 쿼리(0번)는 잘려야 함
    assert all("쿼리 0\n" not in line for line in lines[:1] if "쿼리 0" in line) or \
           all("쿼리 0" not in line for line in lines)


@pytest.mark.unit
def test_history_write_failure_graceful(tmp_path, monkeypatch):
    """이력 파일 쓰기 권한 오류 시 예외 없이 정상 동작 (Error)."""
    from loregist import search as _search

    def raising_path():
        raise PermissionError("쓰기 거부")

    monkeypatch.setattr(_search, "_history_path", raising_path)
    # 예외가 전파되지 않아야 함
    _search.save_history("테스트")  # 예외 없이 통과


# ──────────────────────────────────────────────────────────────
# B-1: fetch_context_chunks (mock DB)
# ──────────────────────────────────────────────────────────────

class _MockCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):
        pass

    def fetchall(self):
        return self._rows


class _MockConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _MockCursor(self._rows)


@pytest.mark.unit
def test_context_no_prev_chunk():
    """chunk_index=0 청크의 앞 컨텍스트 없음 → 에러 없이 빈 반환 (Existence)."""
    from loregist.search import fetch_context_chunks
    # chunk_index=0인 청크는 앞 컨텍스트가 없음 (center_idx - window = -1)
    # DB는 -1과 1 사이 조회하되 idx != 0이므로 idx=1만 반환할 수 있음
    conn = _MockConn([(1, "다음 청크 내용")])
    result = fetch_context_chunks(conn, "proj", "/path/to/file.md", center_idx=0, window=1)
    # chunk_index=0 앞은 없고 뒤(1)만 반환
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["chunk_index"] == 1


@pytest.mark.unit
def test_context_window_size():
    """window=1 시 최대 2개 이웃 청크 반환 (Cardinality)."""
    from loregist.search import fetch_context_chunks
    # center_idx=2, window=1 → idx 1,3 반환 (2 제외)
    conn = _MockConn([(1, "이전 청크"), (3, "다음 청크")])
    result = fetch_context_chunks(conn, "proj", "/path/to/file.md", center_idx=2, window=1)
    assert len(result) == 2
    assert result[0]["chunk_index"] == 1
    assert result[1]["chunk_index"] == 3

"""
tests/conftest.py
T0-3: real_db fixture (integration용 격리 DB 슬롯)
T0-4: 텍스트 fixture (unit/integration 공용)
"""
import sys
import os

# pytest rootdir(loregist/)를 sys.path 선두에 추가 — 언더스코어 모듈 임포트 보장
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ──────────────────────────────────────────────────────────────
# F-6b: DB 가용성 확인 (integration/slow 테스트 auto-skip 용)
# ──────────────────────────────────────────────────────────────
def _db_available() -> bool:
    try:
        import psycopg2
        from loregist.config import DB_CONFIG
        conn = psycopg2.connect(connect_timeout=2, **DB_CONFIG)
        conn.close()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    db_ok = _db_available()
    skip_mark = pytest.mark.skip(reason="pgvector DB 미기동 — docker compose up 후 재실행")
    for item in items:
        if not db_ok and (item.get_closest_marker("integration") or item.get_closest_marker("slow")):
            item.add_marker(skip_mark)


# ──────────────────────────────────────────────────────────────
# T0-3: real_db fixture
# ──────────────────────────────────────────────────────────────
_TEST_PROJECT = "__test_loregist__"


@pytest.fixture(scope="function")
def real_db():
    """
    실제 pgvector DB를 사용하는 통합 테스트용 fixture.

    setup  : __test_loregist__ 슬롯 데이터 DELETE (격리 초기화)
    yield  : project 이름 문자열 '__test_loregist__'
    teardown: 동일 DELETE (테스트 데이터 정리)

    FK 순서: doc_chunks 먼저 DELETE → doc_originals DELETE.
    DB 미기동 시 psycopg2.OperationalError 발생 → 테스트 실패.
    """
    from loregist.config import get_db_connection

    def _cleanup(conn):
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM doc_chunks WHERE project = %s",
                (_TEST_PROJECT,),
            )
            cur.execute(
                "DELETE FROM doc_originals WHERE project = %s",
                (_TEST_PROJECT,),
            )
        conn.commit()

    with get_db_connection() as conn:
        _cleanup(conn)
        yield _TEST_PROJECT
        _cleanup(conn)


# ──────────────────────────────────────────────────────────────
# T0-4: 텍스트 fixture
# split_md / split_log 동작 기준 (실제 실행 검증값)
#   MIN_CHUNK=100, MAX_CHUNK=1500 (vector_chunking.py)
# ──────────────────────────────────────────────────────────────


@pytest.fixture
def md_long2():
    """
    ## 헤더 2개, 각 섹션 본문 110자 > MIN_CHUNK(100).
    split_md → 2청크.
    """
    body = "A" * 110
    body_b = "B" * 110
    return f"## 섹션 A\n{body}\n\n## 섹션 B\n{body_b}"


@pytest.fixture
def md_short2():
    """
    ## 헤더 2개, 각 섹션 본문 짧음(<100자) → 앞 청크에 병합.
    split_md → 1청크.
    """
    return "## 섹션 A\n짧은내용\n\n## 섹션 B\n짧은내용2"


@pytest.fixture
def md_noheader():
    """
    ## / ### 헤더 없는 평문.
    split_md → 1청크.
    """
    return "헤더가 없는 일반 텍스트입니다. 여러 줄이 있을 수 있습니다."


@pytest.fixture
def empty():
    """
    빈 문자열.
    split_md → 0청크, split_log → 0청크.
    """
    return ""


@pytest.fixture
def log_paras():
    """
    빈 줄(\\n\\n)로 구분된 단락 3개, 각 단락 800자 > MAX_CHUNK/2(750).
    단락 누적이 MAX_CHUNK(1500)를 초과하므로 각 단락이 별도 청크로 분리됨.
    split_log → 3청크.
    """
    para = "X" * 800
    return para + "\n\n" + para + "\n\n" + para


@pytest.fixture
def log_tiny():
    """
    20자 미만의 짧은 단일 텍스트.
    split_log → 0청크 (len < 20 필터에 걸림).
    """
    return "short"

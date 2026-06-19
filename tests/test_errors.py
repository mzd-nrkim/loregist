"""
tests/test_errors.py
F-5b — 에러 경로 유닛 테스트

T-E1: DB 연결 실패 시 host:port 포함 안내 메시지 검증
T-E2: 미등록 project cwd → infer_project가 ValueError 발생 검증
"""

import pytest
import psycopg2
from unittest.mock import patch


# ──────────────────────────────────────────────────────────────
# T-E1: DB 연결 실패 메시지에 host/port 또는 안내 문구 포함 확인
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_get_db_connection_error_message_contains_host_port():
    """
    psycopg2.connect가 OperationalError를 raise할 때
    get_db_connection()이 host:port 정보 또는 'pgvector DB 연결 실패' 문구를
    포함한 OperationalError를 re-raise해야 한다.
    """
    from loregist.config import get_db_connection, DB_CONFIG

    with patch("psycopg2.connect", side_effect=psycopg2.OperationalError("timeout")):
        with pytest.raises(psycopg2.OperationalError) as exc_info:
            with get_db_connection():
                pass  # __enter__ 에서 이미 raise됨

    error_msg = str(exc_info.value)
    assert "pgvector DB 연결 실패" in error_msg or DB_CONFIG["host"] in error_msg or str(DB_CONFIG["port"]) in error_msg


# ──────────────────────────────────────────────────────────────
# T-E2: 미등록 project cwd → ValueError
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_infer_project_nonexistent_path_raises_value_error():
    """
    PROJECTS에 등록되지 않은 경로를 cwd로 전달하면
    infer_project()가 ValueError를 발생시켜야 한다.
    """
    from loregist.config import infer_project

    with pytest.raises(ValueError):
        infer_project(cwd="/tmp/nonexistent_project_xyz", explicit=None)


# ──────────────────────────────────────────────────────────────
# G-4a: embed main() 미등록 project → sys.exit(1) (embed.py:101-102)
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_embed_main_unregistered_project_exits(monkeypatch, capsys):
    """G-4a: 미등록 --project 로 embed main() 실행 시 sys.exit(1)."""
    import sys
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", "__no_such_project__"])

    from loregist.embed import main
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "미등록 프로젝트" in captured.err


# ──────────────────────────────────────────────────────────────
# G-4b: search main() 미등록 project → sys.exit(1) (search.py:79-80)
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_search_main_unregistered_project_exits(monkeypatch, capsys):
    """G-4b: 미등록 --project 로 search main() 실행 시 sys.exit(1)."""
    import sys
    monkeypatch.setattr(
        sys, "argv",
        ["vector_search", "테스트쿼리", "--project", "__no_such_project__"],
    )

    from loregist.search import main
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "미등록 프로젝트" in captured.err

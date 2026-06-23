"""
tests/test_cli.py
F-3: CLI main() 오케스트레이션 커버리지 테스트

F-3a: vector_embed.main() dry-run 경로 검증
F-3b: vector_search.main() format_results 출력 형태 검증
F-3c: vector_embed.main() --file 분기 검증 (단건 임베딩, 전체 스캔 미발생, drift 미도달)
"""
import sys
import pytest
from unittest.mock import MagicMock, patch


# ──────────────────────────────────────────────────────────────
# F-3a: embed main() dry-run 테스트
# 검증:
#   - stdout에 "대상 파일:" 포함
#   - stdout에 프로젝트명 "loregist" 포함
#   - 예외 없이 정상 종료 (dry-run이므로 DB 쓰기 없음)
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_embed_main_dry_run(monkeypatch, capsys):
    """F-3a: embed main() --dry-run 실행 → stdout에 '대상 파일:' + 프로젝트명 포함, 예외 없음."""
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", "loregist", "--dry-run"])

    from loregist.embed import main
    main()

    captured = capsys.readouterr()
    assert "대상 파일:" in captured.out, (
        f"stdout에 '대상 파일:' 이 포함되어야 함.\n실제 stdout:\n{captured.out}"
    )
    assert "loregist" in captured.out, (
        f"stdout에 'loregist' 가 포함되어야 함.\n실제 stdout:\n{captured.out}"
    )


# ──────────────────────────────────────────────────────────────
# F-3c: embed main() --file 분기 단위 테스트
# 검증:
#   (1) --file 지정 시 embed_file이 호출되고 discover_embed_files는 호출되지 않음
#   (2) --file 분기가 drift 계산 블록에 도달하지 않음 (early-return 확인)
# ──────────────────────────────────────────────────────────────
def test_embed_main_file_arg_calls_embed_file_not_scan(monkeypatch, tmp_path, capsys):
    """F-3c-1: --file 지정 시 embed_file이 지정 경로로 호출되고 discover_embed_files는 미호출."""
    import loregist.embed as vector_embed

    fake_file = tmp_path / "doc.md"
    fake_file.write_text("# 테스트\n내용")

    fake_conn = MagicMock()
    fake_conn_ctx = MagicMock()
    fake_conn_ctx.__enter__ = MagicMock(return_value=fake_conn)
    fake_conn_ctx.__exit__ = MagicMock(return_value=False)

    called_embed_file = []
    called_discover = []

    def mock_embed_file(conn, project, path):
        called_embed_file.append(path)

    def mock_discover(*args, **kwargs):
        called_discover.append(True)
        return []

    def mock_infer_project(explicit=None):
        return "loregist"

    def mock_get_db_connection():
        return fake_conn_ctx

    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", "loregist", "--file", str(fake_file)])
    monkeypatch.setattr(vector_embed, "embed_file", mock_embed_file)
    monkeypatch.setattr(vector_embed, "discover_embed_files", mock_discover)
    monkeypatch.setattr(vector_embed, "infer_project", mock_infer_project)
    monkeypatch.setattr(vector_embed, "get_db_connection", mock_get_db_connection)
    # PROJECTS는 모듈 수준 직접 binding이므로 별도 patch 필요 (실제 config 없는 환경 대응)
    monkeypatch.setattr(vector_embed, "PROJECTS", {"loregist": {}})

    vector_embed.main()

    assert called_embed_file == [str(fake_file)], (
        f"embed_file이 정확히 1회, 지정 경로로 호출되어야 함. 실제: {called_embed_file}"
    )
    assert not called_discover, "discover_embed_files는 --file 분기에서 호출되지 않아야 함"


def test_embed_main_file_arg_no_drift(monkeypatch, tmp_path):
    """F-3c-2: --file 분기는 early-return으로 drift 계산 블록에 도달하지 않음."""
    import loregist.embed as vector_embed

    fake_file = tmp_path / "doc.md"
    fake_file.write_text("# 테스트\n내용")

    fake_conn = MagicMock()
    fake_conn_ctx = MagicMock()
    fake_conn_ctx.__enter__ = MagicMock(return_value=fake_conn)
    fake_conn_ctx.__exit__ = MagicMock(return_value=False)

    drift_called = []

    def mock_embed_file(conn, project, path):
        pass

    def mock_compute_drift(project):
        drift_called.append(True)
        return []

    def mock_infer_project(explicit=None):
        return "loregist"

    def mock_get_db_connection():
        return fake_conn_ctx

    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", "loregist", "--file", str(fake_file)])
    monkeypatch.setattr(vector_embed, "embed_file", mock_embed_file)
    monkeypatch.setattr(vector_embed, "discover_embed_files", lambda *a, **kw: [])
    monkeypatch.setattr(vector_embed, "infer_project", mock_infer_project)
    monkeypatch.setattr(vector_embed, "get_db_connection", mock_get_db_connection)
    monkeypatch.setattr(vector_embed._drift, "compute_drift", mock_compute_drift)
    # PROJECTS는 모듈 수준 직접 binding이므로 별도 patch 필요 (실제 config 없는 환경 대응)
    monkeypatch.setattr(vector_embed, "PROJECTS", {"loregist": {}})

    vector_embed.main()

    assert not drift_called, "--file early-return 후 drift 계산 블록에 도달하면 안 됨"


# ──────────────────────────────────────────────────────────────
# F-3b: search main() 포맷 테스트
# 검증:
#   - real_db 격리 슬롯에 1개 문서 upsert+chunks embed 후
#   - vector_search.main() 실행
#   - stdout에 "|" (format_results 출력 구분자) 포함
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
@pytest.mark.slow
def test_search_main_format_results(real_db, monkeypatch, capsys):
    """F-3b: search main() 실행 → stdout에 '|' 구분자 포함 (format_results 출력 형태 검증)."""
    import loregist.config as vector_config
    import loregist.search as vector_search
    from loregist.config import get_db_connection, PROJECTS
    from loregist.embed import upsert_original, insert_chunks, embed_documents
    from pathlib import Path

    project = real_db  # "__test_loregist__"
    source_path = "/test/doc_f3b_cli.md"
    source_kind = "md"
    content = (
        "검색 테스트를 위한 문서입니다. "
        "벡터 시맨틱 검색 기능을 CLI main() 경로를 통해 검증합니다. "
        "format_results 함수가 파이프 구분자(|)를 사용하는지 확인합니다."
    )
    file_hash = "f3b3f3b3" * 8

    # 격리 슬롯에 문서 1개 upsert + chunks embed
    with get_db_connection() as conn:
        orig_id = upsert_original(conn, project, source_path, source_kind, content, file_hash)
        embeddings = embed_documents([content])
        insert_chunks(conn, orig_id, project, source_path, source_kind, [content], embeddings)
        conn.commit()

    # PROJECTS에 테스트 슬롯을 임시 등록 (vector_config와 vector_search 모듈 모두 패치)
    patched_projects = dict(PROJECTS)
    patched_projects[project] = {
        "vault": Path("/tmp/__test_loregist__/vault"),
        "archive": Path("/tmp/__test_loregist__/archive"),
        "docs_root": Path("/tmp/__test_loregist__/docs"),
    }
    monkeypatch.setattr(vector_config, "PROJECTS", patched_projects)
    monkeypatch.setattr(vector_search, "PROJECTS", patched_projects)

    # vector_search.main() 호출 — argv 패치
    monkeypatch.setattr(
        sys,
        "argv",
        ["vector_search", "검색 테스트", "--project", "__test_loregist__", "--top-k", "1"],
    )

    from loregist.search import main
    main()

    captured = capsys.readouterr()
    assert "|" in captured.out, (
        f"stdout에 '|' 구분자가 포함되어야 함 (format_results 출력 형태).\n실제 stdout:\n{captured.out}"
    )

"""
tests/test_cli.py
F-3: CLI main() 오케스트레이션 커버리지 테스트

F-3a: vector_embed.main() dry-run 경로 검증
F-3b: vector_search.main() format_results 출력 형태 검증
"""
import sys
import pytest


# ──────────────────────────────────────────────────────────────
# F-3a: embed main() dry-run 테스트
# 검증:
#   - stdout에 "대상 파일:" 포함
#   - stdout에 프로젝트명 포함
#   - 예외 없이 정상 종료 (dry-run이므로 DB 쓰기 없음)
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_embed_main_dry_run(monkeypatch, capsys, tmp_path):
    """F-3a: embed main() --dry-run 실행 → stdout에 '대상 파일:' + 프로젝트명 포함, 예외 없음."""
    import loregist.config as vector_config
    import loregist.embed as vector_embed
    from pathlib import Path

    test_project = "demo"
    # 임시 docs 디렉터리 생성 (dry-run이 파일 목록을 출력하려면 docs_root가 필요)
    docs_root = tmp_path / "dev"
    docs_root.mkdir()

    fake_projects = dict(vector_config.PROJECTS)
    fake_projects[test_project] = {
        "docs_root": docs_root,
        "vault": None,
        "cold": None,
        "done": None,
        "catalog": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setattr(vector_config, "PROJECTS", fake_projects)
    monkeypatch.setattr(vector_embed, "PROJECTS", fake_projects)
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", test_project, "--dry-run"])

    from loregist.embed import main
    main()

    captured = capsys.readouterr()
    assert "대상 파일:" in captured.out, (
        f"stdout에 '대상 파일:' 이 포함되어야 함.\n실제 stdout:\n{captured.out}"
    )
    assert test_project in captured.out, (
        f"stdout에 '{test_project}' 가 포함되어야 함.\n실제 stdout:\n{captured.out}"
    )


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

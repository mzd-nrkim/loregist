"""
tests/test_embed_integration.py
T3 — embed 통합 테스트 (실 pgvector DB 사용)

모든 테스트는 real_db fixture가 제공하는 격리 슬롯(__test_loregist__)에만
데이터를 쓰며, fixture teardown 시 자동 cleanup됨 (실데이터 727건 오염 금지).
"""
import hashlib

import pytest


# ──────────────────────────────────────────────────────────────
# T3-1: upsert_original 단일 삽입
# 검증: id > 0, originals 1행, file_hash 컬럼 일치
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_upsert_original_single(real_db):
    """T3-1: upsert_original 1건 삽입 → id > 0, row count == 1, file_hash 일치."""
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original

    project = real_db
    source_path = "/test/doc_t3_1.md"
    source_kind = "md"
    full_text = "T3-1 테스트 문서 내용입니다."
    file_hash = hashlib.sha256(full_text.encode()).hexdigest()

    with get_db_connection() as conn:
        returned_id = upsert_original(conn, project, source_path, source_kind, full_text, file_hash)
        conn.commit()

        # id > 0
        assert returned_id > 0, f"upsert_original 반환 id가 양의 정수여야 함, 실제: {returned_id}"

        # originals 행 수 == 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_originals WHERE project = %s AND source_path = %s",
                (project, source_path),
            )
            count = cur.fetchone()[0]
        assert count == 1, f"doc_originals 행 수가 1이어야 함, 실제: {count}"

        # file_hash 컬럼 일치
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_hash FROM doc_originals WHERE project = %s AND source_path = %s",
                (project, source_path),
            )
            db_hash = cur.fetchone()[0]
        assert db_hash == file_hash, f"file_hash 불일치. 기대: {file_hash}, DB: {db_hash}"


# ──────────────────────────────────────────────────────────────
# T3-2: upsert 멱등 — 동일 (project, source_path) 재호출
# 검증: originals 행 수 +0, 반환 id 동일
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_upsert_original_idempotent(real_db):
    """T3-2: 동일 (project, source_path) 재호출 시 originals 행수 여전히 1, id 동일."""
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original

    project = real_db
    source_path = "/test/doc_t3_2.md"
    source_kind = "md"
    full_text_v1 = "T3-2 최초 문서 내용"
    file_hash_v1 = hashlib.sha256(full_text_v1.encode()).hexdigest()

    full_text_v2 = "T3-2 업데이트된 문서 내용 (동일 path)"
    file_hash_v2 = hashlib.sha256(full_text_v2.encode()).hexdigest()

    with get_db_connection() as conn:
        # 1차 삽입
        id1 = upsert_original(conn, project, source_path, source_kind, full_text_v1, file_hash_v1)
        conn.commit()

        # 2차 호출 (동일 path, 내용만 변경)
        id2 = upsert_original(conn, project, source_path, source_kind, full_text_v2, file_hash_v2)
        conn.commit()

        # id 동일 (ON CONFLICT DO UPDATE는 같은 id 반환)
        assert id1 == id2, f"upsert 재호출 시 id가 동일해야 함. 1차: {id1}, 2차: {id2}"

        # originals 행 수 여전히 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_originals WHERE project = %s AND source_path = %s",
                (project, source_path),
            )
            count = cur.fetchone()[0]
        assert count == 1, f"upsert 재호출 후 originals 행 수가 1이어야 함, 실제: {count}"


# ──────────────────────────────────────────────────────────────
# T3-3: insert_chunks + embed_documents
# 검증: DB chunks 행수 == split 청크수, embedding 차원 == 384
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
@pytest.mark.slow
def test_insert_chunks_and_embedding_dim(real_db):
    """T3-3: split_md → embed_documents → insert_chunks 후 DB chunks 행수 일치, dim==384."""
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original, insert_chunks, embed_documents
    from loregist.chunking import split_md, hash_file
    import tempfile, os

    project = real_db
    source_path = "/test/doc_t3_3.md"
    source_kind = "md"

    # 2개 청크가 나오는 충분한 문서 (각 섹션 > 100자)
    body_a = "A" * 110
    body_b = "B" * 110
    full_text = f"## 섹션 A\n{body_a}\n\n## 섹션 B\n{body_b}"

    # 임시 파일로 hash_file 사용
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(full_text)
        tmp_path = f.name
    try:
        file_hash = hash_file(tmp_path)
    finally:
        os.unlink(tmp_path)

    chunks = split_md(full_text)
    assert len(chunks) >= 1, "split_md가 청크를 반환해야 함"

    embeddings = embed_documents(chunks)

    with get_db_connection() as conn:
        original_id = upsert_original(conn, project, source_path, source_kind, full_text, file_hash)
        insert_chunks(conn, original_id, project, source_path, source_kind, chunks, embeddings)
        conn.commit()

        # DB chunks 행수 == split 청크수
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_chunks WHERE project = %s AND source_path = %s",
                (project, source_path),
            )
            db_count = cur.fetchone()[0]
        assert db_count == len(chunks), (
            f"DB chunks 행수({db_count})가 split 청크수({len(chunks)})와 일치해야 함"
        )

        # embedding 차원 == 384 (vector_dims 함수 사용)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vector_dims(embedding) FROM doc_chunks WHERE project = %s AND source_path = %s LIMIT 1",
                (project, source_path),
            )
            dim = cur.fetchone()[0]
        assert dim == 384, f"embedding 차원이 384여야 함, 실제: {dim}"


# ──────────────────────────────────────────────────────────────
# T3-4: 빈 파일 및 깨진 바이트 파일 시나리오
# 검증:
#   - 빈 full_text → originals 1행, chunks 0행
#   - 0xFF 바이트 파일 → errors="replace"로 읽어 예외 없이 문자열 반환
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_empty_and_broken_encoding(real_db, tmp_path):
    """T3-4: 빈 파일 → originals 1행/chunks 0행, 깨진 바이트 → 예외 없이 치환 읽기."""
    from pathlib import Path
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original, insert_chunks, embed_documents
    from loregist.chunking import split_md, hash_file

    project = real_db

    # ── 케이스 1: 빈 파일 ─────────────────────────────────────
    empty_path = str(tmp_path / "empty.md")
    Path(empty_path).write_text("", encoding="utf-8")

    full_text_empty = ""
    file_hash_empty = hash_file(empty_path)

    with get_db_connection() as conn:
        orig_id = upsert_original(
            conn, project, "/test/empty_t3_4.md", "md", full_text_empty, file_hash_empty
        )
        conn.commit()

        chunks = split_md(full_text_empty)
        assert chunks == [], "빈 파일의 split_md 결과는 0청크여야 함"

        # originals 1행 유지
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_originals WHERE project = %s AND source_path = %s",
                (project, "/test/empty_t3_4.md"),
            )
            orig_count = cur.fetchone()[0]
        assert orig_count == 1, f"빈 파일 후 originals 1행이어야 함, 실제: {orig_count}"

        # chunks 0행 (insert_chunks를 호출하지 않으므로)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_chunks WHERE project = %s AND source_path = %s",
                (project, "/test/empty_t3_4.md"),
            )
            chunk_count = cur.fetchone()[0]
        assert chunk_count == 0, f"빈 파일 후 chunks 0행이어야 함, 실제: {chunk_count}"

    # ── 케이스 2: 깨진 바이트(0xFF) 파일 → errors="replace"로 예외 없이 읽기 ──
    broken_path = tmp_path / "broken.bin"
    broken_path.write_bytes(b"\xff\xfe\x00invalid utf-8 \xff bytes here")

    # 예외 없이 문자열이 반환되어야 함 (skip 아님)
    result = broken_path.read_text(encoding="utf-8", errors="replace")
    assert isinstance(result, str), "깨진 바이트 파일을 errors='replace'로 읽으면 str이어야 함"
    assert len(result) > 0, "깨진 바이트 파일 읽기 결과가 비어 있으면 안 됨"


# ──────────────────────────────────────────────────────────────
# T3-5: stale 청크 제거 검증
#
# insert_chunks가 INSERT 전에 DELETE를 수행하므로
# v2 재embed 후 stale 청크가 제거됨을 검증한다.
#
# 동작:
#   v1 (청크 2개) insert → v2 (청크 1개, 다른 내용) insert
#   → insert_chunks 진입 시 DELETE FROM doc_chunks WHERE project/source_path 실행
#   → v1 청크 2개 삭제 후 v2 청크 1개만 남음
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
@pytest.mark.slow
def test_stale_chunks_regression(real_db):
    """T3-5: stale 청크가 제거됨을 검증 — v1(2청크) 후 v2(1청크) insert 시 stale이 삭제되어 총 1행만 존재해야 함."""
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original, insert_chunks, embed_documents
    from loregist.chunking import hash_chunk

    project = real_db
    source_path = "/test/doc_t3_5_stale.md"
    source_kind = "md"
    file_hash = "deadbeef" * 8  # 임의 hash (256비트 hex = 64자)

    # v1: 서로 다른 내용의 청크 2개 (hash 중복 방지를 위해 내용 차별화)
    chunk_v1_a = "V1 청크 A: " + "첫번째버전내용" * 10
    chunk_v1_b = "V1 청크 B: " + "두번째버전내용" * 10
    chunks_v1 = [chunk_v1_a, chunk_v1_b]

    # v2: v1과 완전히 다른 내용의 청크 1개
    chunk_v2 = "V2 청크: " + "완전히다른내용" * 10
    chunks_v2 = [chunk_v2]

    with get_db_connection() as conn:
        # v1 삽입 (2청크)
        embeddings_v1 = embed_documents(chunks_v1)
        orig_id = upsert_original(conn, project, source_path, source_kind, "v1 full text", file_hash)
        insert_chunks(conn, orig_id, project, source_path, source_kind, chunks_v1, embeddings_v1)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_chunks WHERE project = %s AND source_path = %s",
                (project, source_path),
            )
            count_after_v1 = cur.fetchone()[0]
        assert count_after_v1 == 2, f"v1 insert 후 2청크여야 함, 실제: {count_after_v1}"

        # v2 삽입 (1청크, 다른 내용) — insert_chunks는 DELETE 없이 INSERT ON CONFLICT DO NOTHING
        embeddings_v2 = embed_documents(chunks_v2)
        upsert_original(conn, project, source_path, source_kind, "v2 full text", file_hash)
        insert_chunks(conn, orig_id, project, source_path, source_kind, chunks_v2, embeddings_v2)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_chunks WHERE project = %s AND source_path = %s",
                (project, source_path),
            )
            count_after_v2 = cur.fetchone()[0]

        # stale 청크가 제거되어 v2 청크 1개만 남아야 함
        assert count_after_v2 == 1, (
            f"stale 청크가 제거되어 총 1행이어야 함, 실제: {count_after_v2}. "
            "insert_chunks 진입 시 DELETE FROM doc_chunks WHERE project/source_path가 실행되어야 함."
        )


# ══════════════════════════════════════════════════════════════
# Phase 2 — 06 embed 신규 TC
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# 2-A. load_existing_hashes()
# ──────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_load_existing_hashes_basic(real_db):
    """T3-6: [R] 정상 hash 로드 — upsert 후 load_existing_hashes 결과 일치."""
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original, load_existing_hashes

    project = real_db
    source_path = "/test/h_t3_6.md"
    file_hash = "abc123"

    with get_db_connection() as conn:
        upsert_original(conn, project, source_path, "md", "내용", file_hash)
        conn.commit()

        result = load_existing_hashes(conn, project)

    assert result == {source_path: file_hash}, (
        f"load_existing_hashes 결과가 {{'{source_path}': '{file_hash}'}}여야 함, 실제: {result}"
    )


@pytest.mark.integration
def test_load_existing_hashes_empty(real_db):
    """T3-7: [B] 빈 DB — load_existing_hashes 결과 {{}}."""
    from loregist.config import get_db_connection
    from loregist.embed import load_existing_hashes

    # real_db fixture가 이미 cleanup된 빈 슬롯을 제공
    with get_db_connection() as conn:
        result = load_existing_hashes(conn, real_db)

    assert result == {}, f"빈 슬롯 load_existing_hashes 결과가 {{}} 이어야 함, 실제: {result}"


# ──────────────────────────────────────────────────────────────
# 2-B. --incremental 모드
# ──────────────────────────────────────────────────────────────

def _make_incremental_env(tmp_path, monkeypatch, real_db):
    """T3-8~11 공통 셋업 헬퍼: tmp_path에 docs 폴더 구성 + monkeypatch.
    vector_embed.PROJECTS는 vector_config에서 직접 name-binding되므로
    vector_embed.PROJECTS도 별도로 patch해야 한다.
    sys.argv는 각 테스트에서 직접 설정한다 (1차 full / 2차 incremental 구분).
    """
    import sys
    import loregist.embed as vector_embed
    import loregist.config as vector_config
    from pathlib import Path

    docs_root = tmp_path / "docs" / "dev"
    docs_root.mkdir(parents=True)
    date_dir = docs_root / "2026-06-15"
    date_dir.mkdir()

    patched_projects = dict(vector_config.PROJECTS)
    patched_projects[real_db] = {
        "vault": None,
        "archive": None,
        "docs_root": docs_root,
    }
    monkeypatch.setattr(vector_config, "PROJECTS", patched_projects)
    # vector_embed.PROJECTS는 모듈 수준 직접 binding이므로 별도 patch 필요
    monkeypatch.setattr(vector_embed, "PROJECTS", patched_projects)
    monkeypatch.setattr(vector_embed, "LOGVAULT_DIR", tmp_path)

    return date_dir


@pytest.mark.integration
@pytest.mark.slow
def test_incremental_only_changed(real_db, tmp_path, monkeypatch, capsys):
    """T3-8: [R] 변경 파일만 처리 — a.md 수정 시 처리=1, 스킵=1."""
    import sys
    import loregist.embed as vector_embed

    date_dir = _make_incremental_env(tmp_path, monkeypatch, real_db)

    # 파일 생성
    file_a = date_dir / "a.md"
    file_b = date_dir / "b.md"
    file_a.write_text("## 섹션 A\n" + "내용A" * 25, encoding="utf-8")
    file_b.write_text("## 섹션 B\n" + "내용B" * 25, encoding="utf-8")

    # 1차 실행 (full 등록 — --incremental 없이)
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", real_db])
    vector_embed.main()
    capsys.readouterr()  # 출력 비우기

    # a.md 내용 수정
    file_a.write_text("## 섹션 A 수정\n" + "수정된내용A" * 25, encoding="utf-8")

    # 2차 실행 (incremental)
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", real_db, "--incremental"])
    vector_embed.main()
    captured = capsys.readouterr()

    assert "처리=1" in captured.out, (
        f"incremental 재실행 시 '처리=1'이 stdout에 포함되어야 함, 실제: {captured.out!r}"
    )
    assert "스킵=1" in captured.out, (
        f"incremental 재실행 시 '스킵=1'이 stdout에 포함되어야 함, 실제: {captured.out!r}"
    )


@pytest.mark.integration
@pytest.mark.slow
def test_incremental_all_unchanged(real_db, tmp_path, monkeypatch, capsys):
    """T3-9: [B] 전부 미변경 — 0건 처리, 2건 스킵."""
    import sys
    import loregist.embed as vector_embed

    date_dir = _make_incremental_env(tmp_path, monkeypatch, real_db)

    file_a = date_dir / "a.md"
    file_b = date_dir / "b.md"
    file_a.write_text("## 섹션 A\n" + "내용A" * 25, encoding="utf-8")
    file_b.write_text("## 섹션 B\n" + "내용B" * 25, encoding="utf-8")

    # 1차 실행 (full 등록)
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", real_db])
    vector_embed.main()
    capsys.readouterr()

    # 변경 없이 2차 실행 (incremental)
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", real_db, "--incremental"])
    vector_embed.main()
    captured = capsys.readouterr()

    assert "처리=0" in captured.out, (
        f"미변경 incremental 실행 시 '처리=0'이 stdout에 포함되어야 함, 실제: {captured.out!r}"
    )
    assert "스킵=2" in captured.out, (
        f"미변경 incremental 실행 시 '스킵=2'이 stdout에 포함되어야 함, 실제: {captured.out!r}"
    )


@pytest.mark.integration
@pytest.mark.slow
def test_incremental_all_new(real_db, tmp_path, monkeypatch, capsys):
    """T3-10: [B] 전부 신규 — full과 동일하게 스킵=0, DB에 chunks 존재."""
    import sys
    import loregist.embed as vector_embed
    from loregist.config import get_db_connection

    date_dir = _make_incremental_env(tmp_path, monkeypatch, real_db)

    file_a = date_dir / "a.md"
    file_b = date_dir / "b.md"
    file_a.write_text("## 섹션 A\n" + "내용A" * 25, encoding="utf-8")
    file_b.write_text("## 섹션 B\n" + "내용B" * 25, encoding="utf-8")

    # 최초 incremental 실행 (빈 슬롯이므로 전부 신규)
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", real_db, "--incremental"])
    vector_embed.main()
    captured = capsys.readouterr()

    assert "스킵=0" in captured.out, (
        f"전부 신규 시 '스킵=0'이 stdout에 포함되어야 함, 실제: {captured.out!r}"
    )

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_chunks WHERE project = %s",
                (real_db,),
            )
            chunk_count = cur.fetchone()[0]

    assert chunk_count > 0, (
        f"전부 신규 incremental 실행 후 doc_chunks 건수가 0 초과여야 함, 실제: {chunk_count}"
    )


@pytest.mark.integration
@pytest.mark.slow
def test_incremental_equals_full(real_db, tmp_path, monkeypatch, capsys):
    """T3-11: [I] incremental vs full 결과 동일성 — chunks 건수 일치 + source_path 집합 일치."""
    import sys
    import loregist.embed as vector_embed
    import loregist.config as vector_config
    from loregist.config import get_db_connection
    from pathlib import Path

    docs_root = tmp_path / "docs" / "dev"
    docs_root.mkdir(parents=True)
    date_dir = docs_root / "2026-06-15"
    date_dir.mkdir()
    file_a = date_dir / "a.md"
    file_b = date_dir / "b.md"
    file_a.write_text("## 섹션 A\n" + "내용A" * 25, encoding="utf-8")
    file_b.write_text("## 섹션 B\n" + "내용B" * 25, encoding="utf-8")

    patched_projects = dict(vector_config.PROJECTS)
    patched_projects[real_db] = {
        "vault": None,
        "archive": None,
        "docs_root": docs_root,
    }
    monkeypatch.setattr(vector_config, "PROJECTS", patched_projects)
    # vector_embed.PROJECTS는 모듈 수준 직접 binding이므로 별도 patch 필요
    monkeypatch.setattr(vector_embed, "PROJECTS", patched_projects)
    monkeypatch.setattr(vector_embed, "LOGVAULT_DIR", tmp_path)

    # (1) full 실행
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", real_db])
    vector_embed.main()
    capsys.readouterr()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM doc_chunks WHERE project = %s", (real_db,))
            full_count = cur.fetchone()[0]
            cur.execute("SELECT DISTINCT source_path FROM doc_chunks WHERE project = %s", (real_db,))
            full_paths = {r[0] for r in cur.fetchall()}

        # cleanup
        with conn.cursor() as cur:
            cur.execute("DELETE FROM doc_chunks WHERE project = %s", (real_db,))
            cur.execute("DELETE FROM doc_originals WHERE project = %s", (real_db,))
        conn.commit()

    # (2) incremental 첫 실행 (빈 슬롯 → 전부 신규)
    monkeypatch.setattr(sys, "argv", ["vector_embed", "--project", real_db, "--incremental"])
    vector_embed.main()
    capsys.readouterr()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM doc_chunks WHERE project = %s", (real_db,))
            incr_count = cur.fetchone()[0]
            cur.execute("SELECT DISTINCT source_path FROM doc_chunks WHERE project = %s", (real_db,))
            incr_paths = {r[0] for r in cur.fetchall()}

    assert full_count == incr_count, (
        f"full과 incremental의 chunks 건수가 일치해야 함. full={full_count}, incremental={incr_count}"
    )
    assert full_paths == incr_paths, (
        f"full과 incremental의 source_path 집합이 일치해야 함. "
        f"full={full_paths}, incremental={incr_paths}"
    )


# ──────────────────────────────────────────────────────────────
# 2-C. write_embed_log()
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_write_embed_log_creates_file(tmp_path, monkeypatch):
    """T3-12: [R] 로그 파일 정상 생성 — mode=full, processed=3, status=OK 포함."""
    import datetime
    import loregist.embed as vector_embed

    monkeypatch.setattr(vector_embed, "LOGVAULT_DIR", tmp_path)

    vector_embed.write_embed_log(
        incremental=False,
        processed=3,
        skipped=0,
        errors=0,
        elapsed=1.2,
    )

    log_path = tmp_path / f"{datetime.date.today()}.log"
    assert log_path.exists(), f"로그 파일이 생성되어야 함: {log_path}"

    content = log_path.read_text(encoding="utf-8")
    assert "mode=full" in content, f"로그에 'mode=full'이 포함되어야 함, 실제: {content!r}"
    assert "processed=3" in content, f"로그에 'processed=3'이 포함되어야 함, 실제: {content!r}"
    assert "status=OK" in content, f"로그에 'status=OK'가 포함되어야 함, 실제: {content!r}"


@pytest.mark.unit
def test_write_embed_log_appends(tmp_path, monkeypatch):
    """T3-13: [R] append 동작 — 2회 연속 호출 시 로그 파일 라인 수 ≥ 2."""
    import datetime
    import loregist.embed as vector_embed

    monkeypatch.setattr(vector_embed, "LOGVAULT_DIR", tmp_path)

    vector_embed.write_embed_log(incremental=False, processed=1, skipped=0, errors=0, elapsed=0.5)
    vector_embed.write_embed_log(incremental=True, processed=2, skipped=1, errors=0, elapsed=0.3)

    log_path = tmp_path / f"{datetime.date.today()}.log"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2, (
        f"로그 파일 라인 수가 2 이상이어야 함 (append 동작 확인), 실제: {len(lines)}"
    )


# ──────────────────────────────────────────────────────────────
# 2-D. hooks/post-commit E2E
# ──────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_hook_triggers_on_docs_dev(tmp_path):
    """T3-14: [E2E] hook 실행 조건 — docs/dev 변경 시 sentinel 생성, exit 0."""
    import subprocess
    from pathlib import Path

    repo = tmp_path / "repo"
    repo.mkdir()

    # git 초기화 + 초기 커밋
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("init", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    # hook 설치: 임베딩 실행 줄을 sentinel touch로 대체
    sentinel = tmp_path / "sentinel_triggered"
    hooks_dir = repo / ".git" / "hooks"
    hook_path = hooks_dir / "post-commit"
    original_hook = Path(__file__).parent.parent / "hooks" / "post-commit"
    hook_script = original_hook.read_text(encoding="utf-8")
    # loregist.embed --incremental 포함 라인을 식별해 sentinel touch로 치환 (부분 문자열 기반으로 견고화)
    embed_marker = "loregist.embed --incremental"
    embed_line = next(
        (line for line in hook_script.splitlines() if embed_marker in line),
        None,
    )
    assert embed_line is not None, (
        f"hooks/post-commit에 '{embed_marker}' 포함 라인이 존재해야 함 — hook 내용 확인 필요"
    )
    lines = hook_script.splitlines()
    new_lines = []
    for line in lines:
        if embed_marker in line:
            new_lines.append(f'touch "{sentinel}"')
        elif line.strip().startswith('cd "$LOREGIST_DIR"'):
            # 존재하지 않는 경로로의 cd를 제거해 set -e abort 방지
            pass
        else:
            new_lines.append(line)
    hook_script_replaced = "\n".join(new_lines)
    # 치환이 실제 적용됐는지 검증 — 무음 no-op 차단
    assert hook_script_replaced != hook_script, (
        f"embed 실행 라인 치환이 적용되지 않음 (no-op). "
        f"embed_line={embed_line!r} 이 hook_script에 포함돼 있어야 함."
    )
    hook_path.write_text(hook_script_replaced, encoding="utf-8")
    hook_path.chmod(0o755)

    # docs/dev 파일 변경 후 커밋
    docs_dir = repo / "docs" / "dev" / "2026-06-15"
    docs_dir.mkdir(parents=True)
    (docs_dir / "test.md").write_text("테스트 문서", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", "add docs/dev file"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"hook exit 0이어야 함, 실제 returncode: {result.returncode}, stderr: {result.stderr}"
    )
    assert sentinel.exists(), (
        f"docs/dev 변경 시 sentinel 파일이 생성되어야 함 (hook trigger 확인): {sentinel}"
    )


@pytest.mark.integration
def test_hook_skips_on_other_path(tmp_path):
    """T3-15: [B] hook 비해당 경로 변경 시 sentinel 미생성, exit 0."""
    import subprocess
    from pathlib import Path

    repo = tmp_path / "repo"
    repo.mkdir()

    # git 초기화 + 초기 커밋
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("init", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    # hook 설치: 임베딩 실행 줄을 sentinel touch로 대체
    sentinel = tmp_path / "sentinel_skipped"
    hooks_dir = repo / ".git" / "hooks"
    hook_path = hooks_dir / "post-commit"
    original_hook = Path(__file__).parent.parent / "hooks" / "post-commit"
    hook_script = original_hook.read_text(encoding="utf-8")
    hook_script = hook_script.replace(
        'PYTHONPATH="$LOREGIST_DIR/src" .venv/bin/python -m loregist.embed --incremental 2>&1 | tee -a "${LOREGIST_WORKSPACE:-$HOME/workspace}/../logvault/embed-log/$(date +%Y-%m-%d).log"',
        f'touch "{sentinel}"',
    )
    hook_path.write_text(hook_script, encoding="utf-8")
    hook_path.chmod(0o755)

    # docs/dev 외 경로(README.md) 변경 후 커밋
    (repo / "README.md").write_text("updated", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", "update README"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"hook exit 0이어야 함, 실제 returncode: {result.returncode}, stderr: {result.stderr}"
    )
    assert not sentinel.exists(), (
        f"docs/dev 외 경로 변경 시 sentinel 파일이 생성되지 않아야 함 (hook skip 확인): {sentinel}"
    )


# ══════════════════════════════════════════════════════════════
# Phase 3 — discover_embed_files 오늘 날짜 폴더 제외/포함 TC
#
# datetime.date는 C 확장 타입이라 monkeypatch.setattr로 직접 교체 불가.
# embed.py가 `import datetime` 후 `datetime.date.today()`를 호출하므로,
# embed 모듈의 datetime 속성을 FakeDatetime 클래스로 통째로 교체한다.
# ══════════════════════════════════════════════════════════════

import datetime as _datetime_mod


def _make_fake_datetime(fixed_date_str: str):
    """지정 날짜를 today()로 반환하는 fake datetime 모듈 대체 클래스를 반환."""
    fixed = _datetime_mod.date.fromisoformat(fixed_date_str)

    class _FakeDate(_datetime_mod.date):
        @classmethod
        def today(cls):
            return fixed

    class _FakeDatetime:
        date = _FakeDate
        datetime = _datetime_mod.datetime

    return _FakeDatetime()


def _setup_discover(tmp_path, monkeypatch, fixed_date_str: str, docs_structure: dict):
    """공통 셋업: docs_root 파일 트리 구성 + datetime·PROJECTS 패치.

    docs_structure: {상대경로: 파일내용} — 예) {"2026-06-19/file.md": "내용"}
    반환값: (embed_mod, test_project, docs_root)
    """
    import loregist.embed as embed_mod
    import loregist.config as config_mod

    docs_root = tmp_path / "dev"
    for rel_path, content in docs_structure.items():
        p = docs_root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    monkeypatch.setattr(embed_mod, "datetime", _make_fake_datetime(fixed_date_str))

    test_project = "__test_discover__"
    patched_projects = {
        test_project: {
            "vault": None,
            "done": None,
            "cold": None,
            "docs_root": docs_root,
        }
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(embed_mod, "PROJECTS", patched_projects)

    return embed_mod, test_project, docs_root


# ──────────────────────────────────────────────────────────────
# B-1: 오늘 날짜 폴더 기본 제외 (include_today=False)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_excludes_today(tmp_path, monkeypatch):
    """B-1: 오늘 날짜 폴더(YYYY-MM-DD/) 안 파일이 기본(include_today=False)에서 제외됨."""
    today_str = "2026-06-19"
    embed_mod, test_project, _ = _setup_discover(
        tmp_path, monkeypatch, today_str,
        {f"{today_str}/file.md": "오늘 문서"},
    )

    result = embed_mod.discover_embed_files(test_project, include_today=False)
    paths = [p for p, _ in result]

    assert not any(today_str in p for p in paths), (
        f"오늘 날짜 폴더({today_str}) 파일이 기본(include_today=False)에서 제외되어야 함, "
        f"실제 포함된 경로: {[p for p in paths if today_str in p]}"
    )


# ──────────────────────────────────────────────────────────────
# B-2: --include-today 시 오늘 날짜 폴더 포함
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_includes_today_when_flag(tmp_path, monkeypatch):
    """B-2: include_today=True 시 오늘 날짜 폴더 안 파일이 포함됨."""
    today_str = "2026-06-19"
    embed_mod, test_project, _ = _setup_discover(
        tmp_path, monkeypatch, today_str,
        {f"{today_str}/file.md": "오늘 문서"},
    )

    result = embed_mod.discover_embed_files(test_project, include_today=True)
    paths = [p for p, _ in result]

    assert any(today_str in p for p in paths), (
        f"include_today=True 시 오늘 날짜 폴더({today_str}) 파일이 포함되어야 함, "
        f"실제 경로 목록: {paths}"
    )


# ──────────────────────────────────────────────────────────────
# B-3: _catalog 파일은 포함되고 kind=='catalog', TOPICS.md·DECISIONS.md 인덱스 파일도 포함
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_includes_catalog_with_catalog_kind(tmp_path, monkeypatch):
    """B-3: _catalog/T-001.md는 kind='catalog'로 포함, TOPICS.md·DECISIONS.md 인덱스 파일도
    kind='catalog'로 포함, include_today=True 시 오늘 날짜 폴더 파일도 포함됨 (교차 검증)."""
    today_str = "2026-06-19"
    embed_mod, test_project, _ = _setup_discover(
        tmp_path, monkeypatch, today_str,
        {
            "_wiki/TOPICS.md": "인덱스 파일 — 포함 대상",
            "_wiki/DECISIONS.md": "결정 인덱스 파일",
            "_wiki/T-001.md": "# T-001\n태스크 카탈로그 문서 내용입니다.",
            f"{today_str}/file.md": "오늘 문서",
        },
    )

    result = embed_mod.discover_embed_files(test_project, include_today=True)
    paths_and_kinds = {p: k for p, k in result}
    paths = list(paths_and_kinds.keys())

    # T-001.md는 포함되고 kind == 'catalog'
    catalog_paths = [p for p in paths if "_wiki" in p]
    assert len(catalog_paths) >= 1, (
        f"_wiki/T-001.md가 결과에 포함되어야 함, 실제 catalog 경로: {catalog_paths}"
    )
    t001_hit = [p for p in catalog_paths if "T-001.md" in p]
    assert len(t001_hit) == 1, (
        f"_wiki/T-001.md가 정확히 1개 포함되어야 함, 실제: {t001_hit}"
    )
    assert paths_and_kinds[t001_hit[0]] == "catalog", (
        f"_wiki/T-001.md의 kind가 'catalog'여야 함, 실제: {paths_and_kinds[t001_hit[0]]!r}"
    )

    # TOPICS.md는 인덱스 파일이지만 포함되고 kind == 'catalog'
    topics_hit = [p for p in paths if "TOPICS.md" in p]
    assert len(topics_hit) == 1, (
        f"_wiki/TOPICS.md가 정확히 1개 포함되어야 함, 실제: {topics_hit}"
    )
    assert paths_and_kinds[topics_hit[0]] == "catalog", (
        f"_wiki/TOPICS.md의 kind가 'catalog'여야 함, 실제: {paths_and_kinds[topics_hit[0]]!r}"
    )

    # DECISIONS.md도 포함되고 kind == 'catalog'
    decisions_hit = [p for p in paths if "DECISIONS.md" in p]
    assert len(decisions_hit) == 1, (
        f"_wiki/DECISIONS.md가 정확히 1개 포함되어야 함, 실제: {decisions_hit}"
    )
    assert paths_and_kinds[decisions_hit[0]] == "catalog", (
        f"_wiki/DECISIONS.md의 kind가 'catalog'여야 함, 실제: {paths_and_kinds[decisions_hit[0]]!r}"
    )

    # 오늘 폴더 파일은 include_today=True라 포함되어야 함 (교차 검증)
    assert any(today_str in p for p in paths), (
        f"include_today=True 시 오늘 날짜 폴더({today_str}) 파일은 포함되어야 함"
    )


# ──────────────────────────────────────────────────────────────
# 추가 경계 케이스: 어제 폴더는 include_today 값과 무관하게 항상 포함
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_yesterday_always_included(tmp_path, monkeypatch):
    """경계: 어제(2026-06-18/) 폴더 파일은 include_today 값과 무관하게 항상 포함."""
    yesterday_str = "2026-06-18"
    embed_mod, test_project, _ = _setup_discover(
        tmp_path, monkeypatch, "2026-06-19",
        {f"{yesterday_str}/file.md": "어제 문서"},
    )

    # include_today=False여도 어제 폴더는 포함
    result_false = embed_mod.discover_embed_files(test_project, include_today=False)
    paths_false = [p for p, _ in result_false]
    assert any(yesterday_str in p for p in paths_false), (
        f"어제 날짜 폴더({yesterday_str}) 파일은 include_today=False여도 포함되어야 함, "
        f"실제 경로: {paths_false}"
    )

    # include_today=True여도 어제 폴더는 포함
    result_true = embed_mod.discover_embed_files(test_project, include_today=True)
    paths_true = [p for p, _ in result_true]
    assert any(yesterday_str in p for p in paths_true), (
        f"어제 날짜 폴더({yesterday_str}) 파일은 include_today=True여도 포함되어야 함, "
        f"실제 경로: {paths_true}"
    )


# ──────────────────────────────────────────────────────────────
# CORRECT: Conformance — today 포맷이 %Y-%m-%d (zero-padded) 확인
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_today_format_zero_padded(tmp_path, monkeypatch):
    """CORRECT/Conformance: 한 자리 월/일(2026-06-09)도 zero-pad로 폴더명과 정확히 일치."""
    today_str = "2026-06-09"
    embed_mod, test_project, _ = _setup_discover(
        tmp_path, monkeypatch, today_str,
        {f"{today_str}/file.md": "한 자리 날짜 문서"},
    )

    # 기본(include_today=False)에서 오늘 폴더 제외 확인
    result = embed_mod.discover_embed_files(test_project, include_today=False)
    paths = [p for p, _ in result]
    assert not any(today_str in p for p in paths), (
        f"한 자리 날짜(2026-06-09) 오늘 폴더도 기본 제외되어야 함, "
        f"실제 포함: {[p for p in paths if today_str in p]}"
    )

    # include_today=True에서 포함 확인
    result_inc = embed_mod.discover_embed_files(test_project, include_today=True)
    paths_inc = [p for p, _ in result_inc]
    assert any(today_str in p for p in paths_inc), (
        f"include_today=True 시 한 자리 날짜(2026-06-09) 오늘 폴더가 포함되어야 함"
    )


# ──────────────────────────────────────────────────────────────
# CORRECT: Existence — docs_root에 날짜 폴더가 없거나 오늘 폴더만 있을 때
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_empty_docs_root(tmp_path, monkeypatch):
    """CORRECT/Existence: docs_root가 비어 있으면 0건, 예외 없이 빈 리스트 반환."""
    embed_mod, test_project, docs_root = _setup_discover(
        tmp_path, monkeypatch, "2026-06-19", {},
    )
    # docs_root 자체는 존재해야 함 (없으면 exists() False로 스캔 생략)
    docs_root.mkdir(parents=True, exist_ok=True)

    result = embed_mod.discover_embed_files(test_project, include_today=False)
    assert result == [], f"빈 docs_root에서 0건이어야 함, 실제: {result}"


@pytest.mark.unit
def test_discover_only_today_folder_returns_zero(tmp_path, monkeypatch):
    """CORRECT/Existence+Cardinality: 오늘 폴더만 있으면 기본 0건, include_today=True는 N건."""
    today_str = "2026-06-19"
    embed_mod, test_project, _ = _setup_discover(
        tmp_path, monkeypatch, today_str,
        {
            f"{today_str}/a.md": "파일 A",
            f"{today_str}/b.md": "파일 B",
        },
    )

    # 기본: 오늘 폴더만 있으면 0건
    result_false = embed_mod.discover_embed_files(test_project, include_today=False)
    assert result_false == [], (
        f"오늘 폴더만 있을 때 기본(include_today=False)는 0건이어야 함, 실제: {result_false}"
    )

    # include_today=True: 2건 포함
    result_true = embed_mod.discover_embed_files(test_project, include_today=True)
    assert len(result_true) == 2, (
        f"include_today=True 시 오늘 폴더 파일 2건이어야 함, 실제: {len(result_true)}"
    )


# ══════════════════════════════════════════════════════════════
# Phase C — catalog 파일 embed 포함 TC
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# C-1: _catalog/T-001.md fixture 추가 후 embed 포함 확인 (단위)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_catalog_file_included_with_catalog_kind(tmp_path, monkeypatch):
    """C-1: _catalog/T-001.md가 discover 결과에 kind='catalog'로 포함됨,
    날짜폴더 파일은 kind='md'임을 교차 확인."""
    embed_mod, test_project, _ = _setup_discover(
        tmp_path, monkeypatch, "2026-06-22",
        {
            "_wiki/T-001.md": "# T-001\n## 목적\n카탈로그 태스크 문서 내용입니다.\n" + "내용" * 30,
            "2026-06-15/normal.md": "날짜폴더 일반 문서",
        },
    )

    result = embed_mod.discover_embed_files(test_project, include_today=False)
    paths_and_kinds = {p: k for p, k in result}
    paths = list(paths_and_kinds.keys())

    # _wiki/T-001.md 포함 확인
    t001_paths = [p for p in paths if "T-001.md" in p]
    assert len(t001_paths) == 1, (
        f"_wiki/T-001.md가 정확히 1개 포함되어야 함, 실제: {t001_paths}"
    )
    assert paths_and_kinds[t001_paths[0]] == "catalog", (
        f"_wiki/T-001.md의 kind가 'catalog'여야 함, 실제: {paths_and_kinds[t001_paths[0]]!r}"
    )

    # 날짜폴더 파일은 kind == 'md'
    date_paths = [p for p in paths if "2026-06-15" in p]
    assert len(date_paths) == 1, (
        f"날짜폴더 파일(2026-06-15/normal.md)이 1개 포함되어야 함, 실제: {date_paths}"
    )
    assert paths_and_kinds[date_paths[0]] == "md", (
        f"날짜폴더 .md 파일의 kind가 'md'여야 함, 실제: {paths_and_kinds[date_paths[0]]!r}"
    )


# ──────────────────────────────────────────────────────────────
# C-3: DB 통합 — upsert_original로 source_kind='catalog' 행 삽입 확인
# ──────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_catalog_upsert_original_source_kind(real_db):
    """C-3a: catalog 문서를 upsert_original로 삽입 시 doc_originals에
    source_kind='catalog' 행이 1개 이상 존재함."""
    import hashlib
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original

    project = real_db
    source_path = "/test/_wiki/T-001.md"
    source_kind = "catalog"
    text = "# T-001\n## 목적\n카탈로그 태스크 문서 내용입니다.\n" + "내용" * 30
    file_hash = hashlib.sha256(text.encode()).hexdigest()

    with get_db_connection() as conn:
        returned_id = upsert_original(conn, project, source_path, source_kind, text, file_hash)
        conn.commit()

        assert returned_id > 0, (
            f"upsert_original 반환 id가 양의 정수여야 함, 실제: {returned_id}"
        )

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_originals WHERE project = %s AND source_kind = 'catalog'",
                (project,),
            )
            count = cur.fetchone()[0]
        assert count >= 1, (
            f"doc_originals에 source_kind='catalog' 행이 1개 이상이어야 함, 실제: {count}"
        )


@pytest.mark.integration
@pytest.mark.slow
def test_catalog_split_md_chunks_inserted(real_db):
    """C-3b: catalog .md 텍스트를 split_md로 청킹 → insert_chunks → doc_chunks에 행 존재.
    split_md 청킹 회귀 검증: catalog 문서도 .md 확장자 기준으로 split_md가 동작함을 확인."""
    import hashlib
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original, insert_chunks, embed_documents
    from loregist.chunking import split_md

    project = real_db
    source_path = "/test/_wiki/T-002.md"
    source_kind = "catalog"

    body_a = "A" * 110
    body_b = "B" * 110
    text = f"## 섹션 A\n{body_a}\n\n## 섹션 B\n{body_b}"
    file_hash = hashlib.sha256(text.encode()).hexdigest()

    chunks = split_md(text)
    assert len(chunks) >= 1, "catalog .md split_md가 청크를 반환해야 함"

    embeddings = embed_documents(chunks)

    with get_db_connection() as conn:
        original_id = upsert_original(conn, project, source_path, source_kind, text, file_hash)
        insert_chunks(conn, original_id, project, source_path, source_kind, chunks, embeddings)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM doc_chunks WHERE project = %s AND source_path = %s",
                (project, source_path),
            )
            db_count = cur.fetchone()[0]
        assert db_count == len(chunks), (
            f"doc_chunks 행수({db_count})가 split_md 청크수({len(chunks)})와 일치해야 함"
        )


# ══════════════════════════════════════════════════════════════
# Phase 2 E — handbook 임베딩 TC
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# E-1-1: discover_embed_files — handbook 파일이 kind='handbook'로 포함
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_includes_handbook_sources(tmp_path, monkeypatch):
    """E-1-1: handbook에 설정된 파일이 discover_embed_files 결과에 kind='handbook'로 포함됨."""
    import loregist.embed as embed_mod
    import loregist.config as config_mod

    # handbook 파일은 docs_root 밖 별도 디렉터리에 생성
    handbook_dir = tmp_path / "handbook"
    handbook_dir.mkdir()
    handbook_file = handbook_dir / "page.md"
    handbook_file.write_text("# Handbook 페이지\n" + "W" * 100, encoding="utf-8")

    # docs_root는 별도로 구성 (빈 디렉터리)
    docs_root = tmp_path / "dev"
    docs_root.mkdir()

    test_project = "__test_handbook_e1_1__"
    patched_projects = {
        test_project: {
            "vault": None,
            "done": None,
            "cold": None,
            "docs_root": docs_root,
            "handbook": [
                {"path": handbook_file, "writable": False, "update_when": None}
            ],
        }
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(embed_mod, "PROJECTS", patched_projects)

    result = embed_mod.discover_embed_files(test_project)
    handbook_entries = [(p, k) for p, k in result if k == "handbook"]

    assert len(handbook_entries) >= 1, (
        f"handbook 파일이 kind='handbook'로 1건 이상 포함되어야 함, 실제: {result}"
    )
    handbook_paths = [p for p, _ in handbook_entries]
    assert any(str(handbook_file) in p for p in handbook_paths), (
        f"handbook_file({handbook_file})이 handbook 항목에 포함되어야 함, 실제 handbook 항목: {handbook_entries}"
    )


# ──────────────────────────────────────────────────────────────
# E-1-2: discover_embed_files — 존재하지 않는 handbook 경로는 스킵
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_skips_nonexistent_handbook_path(tmp_path, monkeypatch):
    """E-1-2: handbook에 존재하지 않는 경로를 설정하면 discover 결과에 handbook 항목이 0건임."""
    import loregist.embed as embed_mod
    import loregist.config as config_mod

    docs_root = tmp_path / "dev"
    docs_root.mkdir()

    nonexistent_path = tmp_path / "handbook" / "ghost.md"  # 파일 생성 안 함

    test_project = "__test_handbook_e1_2__"
    patched_projects = {
        test_project: {
            "vault": None,
            "done": None,
            "cold": None,
            "docs_root": docs_root,
            "handbook": [
                {"path": nonexistent_path, "writable": False, "update_when": None}
            ],
        }
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(embed_mod, "PROJECTS", patched_projects)

    result = embed_mod.discover_embed_files(test_project)
    handbook_entries = [(p, k) for p, k in result if k == "handbook"]

    assert len(handbook_entries) == 0, (
        f"존재하지 않는 handbook 경로는 스킵되어 handbook 항목이 0건이어야 함, 실제: {handbook_entries}"
    )


# ──────────────────────────────────────────────────────────────
# E-1-3: discover_embed_files — vault와 handbook 중복 파일은 vault 우선
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_deduplicates_handbook_and_vault(tmp_path, monkeypatch):
    """E-1-3: vault 안의 파일을 handbook에도 추가하면 해당 파일이 1건만 포함되고
    kind는 vault 스캔 결과('md' 또는 'log')가 우선됨 (handbook이 아님)."""
    import loregist.embed as embed_mod
    import loregist.config as config_mod

    # vault 디렉터리에 파일 생성
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    shared_file = vault_dir / "shared.md"
    shared_file.write_text("# 공유 파일\n" + "S" * 100, encoding="utf-8")

    docs_root = tmp_path / "dev"
    docs_root.mkdir()

    test_project = "__test_handbook_e1_3__"
    patched_projects = {
        test_project: {
            "vault": vault_dir,
            "done": None,
            "cold": None,
            "docs_root": docs_root,
            "handbook": [
                {"path": shared_file, "writable": False, "update_when": None}
            ],
        }
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(embed_mod, "PROJECTS", patched_projects)

    result = embed_mod.discover_embed_files(test_project)
    shared_entries = [(p, k) for p, k in result if str(shared_file) in p]

    # 1건만 포함되어야 함 (중복 제거)
    assert len(shared_entries) == 1, (
        f"vault+handbook 중복 파일은 1건만 포함되어야 함, 실제: {shared_entries}"
    )

    # kind는 vault 우선 ('md' 또는 'log'), handbook이 아님
    _, kind = shared_entries[0]
    assert kind in ("md", "log"), (
        f"vault에서 먼저 수집된 파일의 kind는 'md' 또는 'log'여야 함 (handbook 아님), 실제: {kind!r}"
    )
    assert kind != "handbook", (
        f"vault 파일이 handbook에도 있을 때 kind가 'handbook'가 되어서는 안 됨, 실제: {kind!r}"
    )


# ──────────────────────────────────────────────────────────────
# E-2-1: embed_file — handbook 파일 임베딩 시 source_kind='handbook'로 DB 저장
# ──────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_embed_handbook_source_kind_stored(real_db, tmp_path, monkeypatch):
    """E-2-1: handbook 파일을 embed_file()로 임베딩하면 doc_originals에 source_kind='handbook'로 저장됨."""
    import loregist.embed as vector_embed
    import loregist.config as vector_config
    from loregist.config import get_db_connection

    # handbook 파일 생성
    handbook_dir = tmp_path / "handbook"
    handbook_dir.mkdir()
    handbook_file = handbook_dir / "handbook_test.md"
    handbook_file.write_text("# Handbook 테스트\n" + "A" * 200, encoding="utf-8")

    # PROJECTS에 real_db 슬롯에 handbook 포함해 패치
    patched_projects = dict(vector_config.PROJECTS)
    patched_projects[real_db] = {
        "vault": None,
        "done": None,
        "cold": None,
        "docs_root": None,
        "handbook": [{"path": handbook_file, "writable": False, "update_when": None}],
    }
    monkeypatch.setattr(vector_config, "PROJECTS", patched_projects)
    monkeypatch.setattr(vector_embed, "PROJECTS", patched_projects)

    # embed_file 직접 호출
    with get_db_connection() as conn:
        vector_embed.embed_file(conn, real_db, str(handbook_file))

        # DB에서 source_kind 확인
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_kind FROM doc_originals WHERE project = %s AND source_path = %s",
                (real_db, str(handbook_file)),
            )
            row = cur.fetchone()

    assert row is not None, (
        f"embed_file 호출 후 doc_originals에 행이 존재해야 함 (project={real_db}, path={handbook_file})"
    )
    assert row[0] == "handbook", (
        f"handbook 파일의 source_kind가 'handbook'여야 함, 실제: {row[0]!r}"
    )

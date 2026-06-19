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
    # 이 repo의 hooks/post-commit 템플릿을 기준으로 E2E 테스트용 hook 생성
    project_root = Path(__file__).parent.parent
    original_hook = project_root / "hooks" / "post-commit"
    hook_script = original_hook.read_text(encoding="utf-8")
    # 임베딩 실행 라인을 sentinel touch로 치환
    hook_script = hook_script.replace(
        'PYTHONPATH="$LOREGIST_DIR/src" .venv/bin/python -m loregist.embed --incremental 2>&1 | tee -a "$LOG_DIR/$(date +%Y-%m-%d).log"',
        f'touch "{sentinel}"',
    )
    hook_path.write_text(hook_script, encoding="utf-8")
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
    # 이 repo의 hooks/post-commit 템플릿을 기준으로 E2E 테스트용 hook 생성
    project_root = Path(__file__).parent.parent
    original_hook = project_root / "hooks" / "post-commit"
    hook_script = original_hook.read_text(encoding="utf-8")
    hook_script = hook_script.replace(
        'PYTHONPATH="$LOREGIST_DIR/src" .venv/bin/python -m loregist.embed --incremental 2>&1 | tee -a "$LOG_DIR/$(date +%Y-%m-%d).log"',
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

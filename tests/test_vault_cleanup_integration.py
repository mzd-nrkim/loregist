"""
tests/test_vault_cleanup_integration.py
vault_cleanup.py 통합 테스트 (실 pgvector DB 사용)

TC Right (정확성):
  - test_verify_in_db_exists: doc_originals에 1건 임베딩 후 verify_in_db() → True
  - test_verify_in_db_not_exists: 임베딩 안 된 경로로 verify_in_db() → False
  - test_cold_files_included_in_comparison: vault 1건 + cold/ 1건 → 대조 결과에 둘 다 포함
  - test_cold_file_becomes_candidate: cold/ 파일이 보존기간 초과 + DB OK → 삭제 후보에 포함

TC Boundary (경계값):
  - test_vault_cleanup_not_opted_in: vault_cleanup opt-in 안 한 프로젝트 실행 → 안내 후 종료
  - test_vault_empty_dir: vault 디렉토리가 비어 있을 때 → 후보 0건, 에러 없이 종료
  - test_retention_zero_all_files_candidate: 보존일 0 → 모든 DB 원문 파일이 삭제 후보

TC Error (오류 조건):
  - test_verify_db_missing_row: doc_originals에 없는 vault 파일은 삭제 후보에서 제외

TC Existence (존재성):
  - test_existence_not_in_db_excluded_from_candidates: doc_originals에 없는 파일은 후보 제외

TC Cardinality (수량):
  - test_cardinality_dry_run_summary: 삭제 후보 0/1/N건 → dry-run 요약 출력 정확성

TC Time (타이밍):
  - test_time_boundary_exactly_retention_days: 정확히 보존일 경계에서 후보 포함/제외 동작
"""

import hashlib
import os
import sys
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────
# TC Right: test_verify_in_db_exists
# doc_originals에 1건 임베딩(upsert) 후 verify_in_db() → True 반환
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_verify_in_db_exists(real_db, tmp_path):
    """
    [R] doc_originals에 1건 upsert 후 verify_in_db() → True.
    full_text 비어있지 않음 + file_hash 일치 둘 다 만족하는 경우 True.
    """
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original
    from loregist.vault_cleanup import verify_in_db

    project = real_db

    # 테스트 파일 생성 (실제 파일이 필요: verify_in_db가 hash_file을 호출함)
    test_file = tmp_path / "test_doc.md"
    full_text = "verify_in_db 테스트 문서 내용입니다. " * 5
    test_file.write_text(full_text, encoding="utf-8")

    file_hash = hashlib.sha256(full_text.encode()).hexdigest()

    with get_db_connection() as conn:
        # upsert_original로 DB에 원문 저장
        upsert_original(conn, project, str(test_file), "md", full_text, file_hash)
        conn.commit()

        # verify_in_db: full_text 비어있지 않음 + file_hash 일치 → True
        result = verify_in_db(conn, project, test_file)

    assert result is True, (
        f"DB에 원문이 저장되어 있고 file_hash가 일치하면 verify_in_db()는 True여야 함, 실제: {result}"
    )


# ──────────────────────────────────────────────────────────────
# TC Right: test_verify_in_db_not_exists
# 임베딩 안 된 경로로 verify_in_db() → False
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_verify_in_db_not_exists(real_db, tmp_path):
    """
    [R] doc_originals에 없는 경로로 verify_in_db() → False.
    row가 없으면 False 반환.
    """
    from loregist.config import get_db_connection
    from loregist.vault_cleanup import verify_in_db

    project = real_db

    # 파일은 존재하지만 DB에는 등록되지 않은 경로
    test_file = tmp_path / "not_in_db.md"
    test_file.write_text("DB에 없는 파일 내용", encoding="utf-8")

    with get_db_connection() as conn:
        result = verify_in_db(conn, project, test_file)

    assert result is False, (
        f"DB에 원문이 없으면 verify_in_db()는 False여야 함, 실제: {result}"
    )


# ──────────────────────────────────────────────────────────────
# TC Boundary: test_vault_cleanup_not_opted_in
# vault_cleanup opt-in 안 한 프로젝트로 실행 → 안내 후 종료 (exit 0)
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_vault_cleanup_not_opted_in(capsys, monkeypatch):
    """
    [B] vault_cleanup opt-in이 없는 프로젝트로 run() 실행 → INFO 안내 후 sys.exit(0).
    """
    from loregist.vault_cleanup import run

    # 실제 프로젝트 중 vault_cleanup이 off인 것 사용 (기본 off = loregist)
    # run()은 opt-in 없으면 sys.exit(0) 호출
    with pytest.raises(SystemExit) as exc_info:
        run("loregist", dry_run=True)

    assert exc_info.value.code == 0, (
        f"opt-in 없는 프로젝트는 sys.exit(0)을 호출해야 함, 실제: {exc_info.value.code}"
    )

    # stderr에 안내 메시지가 출력되어야 함
    captured = capsys.readouterr()
    assert "vault_cleanup opt-in" in captured.err, (
        f"stderr에 'vault_cleanup opt-in' 안내 메시지가 포함되어야 함, 실제: {captured.err!r}"
    )


# ──────────────────────────────────────────────────────────────
# TC Boundary: test_vault_empty_dir
# vault 디렉토리가 비어 있을 때 → 후보 0건, 에러 없이 종료
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_vault_empty_dir(tmp_path, monkeypatch):
    """
    [B] vault 디렉토리가 비어 있을 때 → 후보 0건, 에러 없이 종료.
    _collect_vault_files가 빈 리스트를 반환 → run()이 INFO 출력 후 정상 반환.
    """
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod

    # vault_cleanup opt-in 프로젝트를 monkeypatch로 생성
    empty_vault = tmp_path / "empty_vault"
    empty_vault.mkdir()

    test_project = "__test_vault_empty__"
    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": empty_vault,
        "cold": None,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": 90,
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    # 빈 vault 디렉토리 → 에러 없이 정상 반환 (SystemExit 없음)
    # run()은 files가 비어 있으면 INFO 출력 후 return
    vc_mod.run(test_project, dry_run=True)  # 예외 없이 정상 종료해야 함


# ──────────────────────────────────────────────────────────────
# TC Error: test_verify_db_missing_row
# doc_originals에 없는 vault 파일은 삭제 후보에서 제외
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_verify_db_missing_row(real_db, tmp_path, monkeypatch, capsys):
    """
    [E] doc_originals에 없는 vault 파일은 삭제 후보에서 제외됨.
    verify_in_db=False → candidates에 포함되지 않음 → dry-run 출력에 없음.
    """
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod

    # vault 디렉토리에 DB에 없는 파일 1개 생성
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    missing_file = vault_dir / "missing_in_db.md"
    missing_file.write_text("DB에 없는 vault 파일 내용", encoding="utf-8")

    # mtime을 충분히 오래된 것으로 설정 (보존 기간 초과 시뮬레이션)
    import time
    old_time = time.time() - (91 * 86400)  # 91일 전
    os.utime(missing_file, (old_time, old_time))

    test_project = real_db
    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": vault_dir,
        "cold": None,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": 90,
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    # DB에 파일이 없는 상태에서 dry-run 실행
    vc_mod.run(test_project, dry_run=True)
    captured = capsys.readouterr()

    # "미저장: 1건" — DB에 없는 파일이 미저장으로 집계되어야 함
    assert "미저장: 1건" in captured.out, (
        f"DB에 없는 파일은 '미저장: 1건'으로 집계되어야 함, 실제 stdout: {captured.out!r}"
    )

    # 삭제 후보에 포함되지 않아야 함 (candidates = 0)
    assert "삭제 후보: 0건" in captured.out, (
        f"DB에 없는 파일은 삭제 후보에서 제외되어야 함(삭제 후보: 0건), 실제: {captured.out!r}"
    )


# ──────────────────────────────────────────────────────────────
# TC Right: test_cold_files_included_in_comparison
# vault 1건 + cold/ 1건 입력 시 둘 다 대조 결과에 나타나는지 확인
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_cold_files_included_in_comparison(real_db, tmp_path, monkeypatch, capsys):
    """
    [R] vault/ 1건 + cold/ 1건 → 대조 결과 총 2건으로 집계.
    cold/ 파일도 _collect_vault_files가 수집해 DB 대조 대상에 포함돼야 함.
    둘 다 DB에 없는 상태 → 미저장: 2건, 삭제 후보: 0건.
    """
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod

    # vault 디렉토리에 파일 1건
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    vault_file = vault_dir / "vault_doc.md"
    vault_file.write_text("vault 파일 내용", encoding="utf-8")

    # cold 디렉토리에 파일 1건 (vault의 자식이 아닌 별도 경로)
    cold_dir = tmp_path / "cold"
    cold_dir.mkdir()
    cold_file = cold_dir / "cold_doc.md"
    cold_file.write_text("cold 파일 내용", encoding="utf-8")

    test_project = real_db
    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": vault_dir,
        "cold": cold_dir,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": 90,
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    vc_mod.run(test_project, dry_run=True)
    captured = capsys.readouterr()

    # 총 2건 대조 (vault 1 + cold 1)
    assert "총 2건" in captured.out, (
        f"vault 1건 + cold 1건 → 총 2건으로 집계되어야 함, 실제: {captured.out!r}"
    )
    # 둘 다 DB에 없으므로 미저장: 2건
    assert "미저장: 2건" in captured.out, (
        f"DB에 없는 파일 2건 → 미저장: 2건이어야 함, 실제: {captured.out!r}"
    )


# ──────────────────────────────────────────────────────────────
# TC Right: test_cold_file_becomes_candidate
# cold/ 파일이 보존기간 초과 + DB 원문 존재 → 삭제 후보에 포함
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_cold_file_becomes_candidate(real_db, tmp_path, monkeypatch, capsys):
    """
    [R] cold/ 파일이 DB OK + 보존 기간 초과 → 삭제 후보에 포함됨.
    vault_cleanup 대상이 vault에만 한정되지 않고 cold/도 포함됨을 검증.
    """
    import time
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original
    import hashlib

    # cold 파일 생성 (별도 디렉토리, vault의 자식이 아님)
    cold_dir = tmp_path / "cold"
    cold_dir.mkdir()
    cold_file = cold_dir / "old_cold_doc.md"
    full_text = "cold 파일 원문 내용 — DB에 저장되어야 함. " * 5
    cold_file.write_text(full_text, encoding="utf-8")

    # mtime을 91일 전으로 설정 (보존 기간 90일 초과)
    old_time = time.time() - (91 * 86400)
    os.utime(cold_file, (old_time, old_time))

    file_hash = hashlib.sha256(full_text.encode()).hexdigest()
    test_project = real_db

    # DB에 cold 파일 원문 저장
    with get_db_connection() as conn:
        upsert_original(conn, test_project, str(cold_file), "md", full_text, file_hash)
        conn.commit()

    # vault는 비어있는 디렉토리, cold만 파일 존재
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": vault_dir,
        "cold": cold_dir,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": 90,
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    vc_mod.run(test_project, dry_run=True)
    captured = capsys.readouterr()

    # cold 파일이 삭제 후보에 포함되어야 함
    assert "삭제 후보: 1건" in captured.out, (
        f"cold/ 파일이 보존기간 초과 + DB OK → 삭제 후보: 1건이어야 함, 실제: {captured.out!r}"
    )
    assert str(cold_file) in captured.out, (
        f"dry-run 출력에 cold 파일 경로가 포함되어야 함, 실제: {captured.out!r}"
    )


# ──────────────────────────────────────────────────────────────
# TC Boundary: test_retention_zero_all_files_candidate
# 보존일 0 → DB 원문 존재하는 모든 파일이 삭제 후보
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_retention_zero_all_files_candidate(real_db, tmp_path, monkeypatch, capsys):
    """
    [B] 보존일 0(vault_cleanup=0) → DB OK인 모든 파일이 보존 기간 초과 후보가 됨.
    elapsed >= 0 는 항상 참이므로 DB 원문 존재 파일 전부가 후보.
    """
    import hashlib
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    # 파일 2건: 둘 다 방금 생성된 파일 (mtime = 지금) → 경과일 ≈ 0
    files_data = []
    for i in range(2):
        f = vault_dir / f"fresh_doc_{i}.md"
        content = f"신규 파일 {i} 내용입니다. " * 5
        f.write_text(content, encoding="utf-8")
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        files_data.append((f, content, file_hash))

    test_project = real_db
    with get_db_connection() as conn:
        for f, content, fhash in files_data:
            upsert_original(conn, test_project, str(f), "md", content, fhash)
        conn.commit()

    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": vault_dir,
        "cold": None,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": 0,  # 보존일 0 → 모든 파일이 즉시 후보
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    vc_mod.run(test_project, dry_run=True)
    captured = capsys.readouterr()

    # 보존일 0이면 경과일 ≥ 0은 항상 참 → DB OK 파일 2건 모두 후보
    assert "삭제 후보: 2건" in captured.out, (
        f"보존일 0 → DB OK 파일 2건 모두 삭제 후보여야 함, 실제: {captured.out!r}"
    )


# ──────────────────────────────────────────────────────────────
# TC Existence: test_existence_not_in_db_excluded_from_candidates
# doc_originals에 없는 vault 파일은 삭제 후보에서 제외 (명시적 Existence TC)
# (test_verify_db_missing_row와 보완 관계 — 이 TC는 vault + DB OK 혼합 케이스)
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_existence_not_in_db_excluded_from_candidates(real_db, tmp_path, monkeypatch, capsys):
    """
    [X] doc_originals에 없는 파일은 삭제 후보 제외, DB에 있는 파일만 후보 선정.
    vault 파일 2건: 1건은 DB OK + 기간 초과, 1건은 DB 미존재 + 기간 초과.
    → 삭제 후보: 1건 (DB OK 파일만).
    """
    import time
    import hashlib
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    # 파일 1: DB에 저장 + 기간 초과
    db_file = vault_dir / "in_db.md"
    content_db = "DB에 저장된 파일 내용입니다. " * 5
    db_file.write_text(content_db, encoding="utf-8")
    old_time = time.time() - (91 * 86400)
    os.utime(db_file, (old_time, old_time))
    file_hash = hashlib.sha256(content_db.encode()).hexdigest()

    test_project = real_db
    with get_db_connection() as conn:
        upsert_original(conn, test_project, str(db_file), "md", content_db, file_hash)
        conn.commit()

    # 파일 2: DB에 없음 + 기간 초과
    no_db_file = vault_dir / "not_in_db.md"
    no_db_file.write_text("DB에 없는 파일 내용", encoding="utf-8")
    os.utime(no_db_file, (old_time, old_time))

    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": vault_dir,
        "cold": None,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": 90,
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    vc_mod.run(test_project, dry_run=True)
    captured = capsys.readouterr()

    # DB에 있는 파일 1건만 후보
    assert "삭제 후보: 1건" in captured.out, (
        f"DB에 있는 파일 1건만 후보여야 함, 실제: {captured.out!r}"
    )
    # DB에 없는 파일은 미저장으로 집계
    assert "미저장: 1건" in captured.out, (
        f"DB 미존재 파일은 미저장: 1건으로 집계되어야 함, 실제: {captured.out!r}"
    )
    # dry-run 후보 목록에 DB 파일만 포함
    assert str(db_file) in captured.out, (
        f"dry-run 목록에 DB OK 파일 경로가 포함되어야 함, 실제: {captured.out!r}"
    )
    assert str(no_db_file) not in captured.out, (
        f"dry-run 목록에 DB 미존재 파일이 포함되면 안 됨, 실제: {captured.out!r}"
    )


# ──────────────────────────────────────────────────────────────
# TC Cardinality: test_cardinality_dry_run_summary
# 삭제 후보 0개/1개/N개 → dry-run 요약 출력이 정확한지 확인
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
@pytest.mark.parametrize("n_candidates", [0, 1, 3])
def test_cardinality_dry_run_summary(real_db, tmp_path, monkeypatch, capsys, n_candidates):
    """
    [C] 삭제 후보 0/1/N건 → dry-run 요약 '삭제 후보: {n}건' 정확히 출력.
    - n=0: DB 원문 없는 파일만 → 후보 0건
    - n=1: DB OK + 기간 초과 파일 1건
    - n=3: DB OK + 기간 초과 파일 3건
    """
    import time
    import hashlib
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    test_project = real_db
    old_time = time.time() - (91 * 86400)  # 91일 전

    if n_candidates == 0:
        # DB에 없는 파일 1건 (기간 초과여도 후보 아님)
        f = vault_dir / "no_db_file.md"
        f.write_text("DB에 없는 파일", encoding="utf-8")
        os.utime(f, (old_time, old_time))
    else:
        # n_candidates건의 DB OK + 기간 초과 파일
        with get_db_connection() as conn:
            for i in range(n_candidates):
                f = vault_dir / f"candidate_{i}.md"
                content = f"삭제 후보 파일 {i} 내용입니다. " * 5
                f.write_text(content, encoding="utf-8")
                os.utime(f, (old_time, old_time))
                fhash = hashlib.sha256(content.encode()).hexdigest()
                upsert_original(conn, test_project, str(f), "md", content, fhash)
            conn.commit()

    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": vault_dir,
        "cold": None,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": 90,
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    vc_mod.run(test_project, dry_run=True)
    captured = capsys.readouterr()

    assert f"삭제 후보: {n_candidates}건" in captured.out, (
        f"n_candidates={n_candidates}일 때 '삭제 후보: {n_candidates}건' 출력되어야 함, "
        f"실제: {captured.out!r}"
    )


# ──────────────────────────────────────────────────────────────
# TC Time: test_time_boundary_exactly_retention_days
# mtime 기준 경계값(정확히 보존일)에서 포함/제외 동작 확인
# elapsed >= retention_days 조건 → 정확히 retention_days 경과 시 후보 포함
# ──────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_time_boundary_exactly_retention_days(real_db, tmp_path, monkeypatch, capsys):
    """
    [T] mtime 기준 경과일 경계값 테스트.
    - 정확히 90일 경과 파일 → 후보 포함 (elapsed >= 90, 등호 포함)
    - 89.9일 경과 파일 → 후보 제외 (elapsed < 90)
    두 파일 모두 DB OK 상태.
    """
    import time
    import hashlib
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod
    from loregist.config import get_db_connection
    from loregist.embed import upsert_original

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    test_project = real_db
    now = time.time()
    retention_days = 90

    # 파일 A: 정확히 90일 전 (경계값 — 후보에 포함되어야 함)
    file_exact = vault_dir / "exact_boundary.md"
    content_exact = "정확히 90일 경과 파일 내용입니다. " * 5
    file_exact.write_text(content_exact, encoding="utf-8")
    exact_time = now - (retention_days * 86400)
    os.utime(file_exact, (exact_time, exact_time))
    hash_exact = hashlib.sha256(content_exact.encode()).hexdigest()

    # 파일 B: 89.9일 전 (경계값 미만 — 후보에서 제외되어야 함)
    file_under = vault_dir / "under_boundary.md"
    content_under = "89.9일 경과 파일 내용입니다. " * 5
    file_under.write_text(content_under, encoding="utf-8")
    under_time = now - (89.9 * 86400)
    os.utime(file_under, (under_time, under_time))
    hash_under = hashlib.sha256(content_under.encode()).hexdigest()

    with get_db_connection() as conn:
        upsert_original(conn, test_project, str(file_exact), "md", content_exact, hash_exact)
        upsert_original(conn, test_project, str(file_under), "md", content_under, hash_under)
        conn.commit()

    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": vault_dir,
        "cold": None,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": retention_days,
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    vc_mod.run(test_project, dry_run=True)
    captured = capsys.readouterr()

    # 정확히 90일 경과 파일 1건만 후보
    assert "삭제 후보: 1건" in captured.out, (
        f"정확히 90일 경과 파일만 후보여야 함(89.9일은 제외), 실제: {captured.out!r}"
    )
    # 경계값 파일은 목록에 포함
    assert str(file_exact) in captured.out, (
        f"정확히 90일 경과 파일이 dry-run 목록에 있어야 함, 실제: {captured.out!r}"
    )
    # 미달 파일은 목록에 없음
    assert str(file_under) not in captured.out, (
        f"89.9일 경과 파일은 dry-run 목록에 없어야 함, 실제: {captured.out!r}"
    )


# ──────────────────────────────────────────────────────────────
# TC Error: test_db_connection_failure
# DB 연결 실패 시 에러 메시지 출력 후 sys.exit(1) — DB 불필요 단위 테스트
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_db_connection_failure(tmp_path, monkeypatch, capsys):
    """
    [E] DB 연결 실패 시 vault_cleanup.run()이 에러 메시지를 출력하고 sys.exit(1)을 호출.
    get_db_connection을 monkeypatch로 예외를 발생시켜 graceful error 처리를 검증.
    catalog_gen은 DB를 사용하지 않으므로 이 TC는 vault_cleanup(E)만 대상으로 함.
    """
    import loregist.vault_cleanup as vc_mod
    import loregist.config as config_mod

    # vault 디렉토리에 파일 1건 (opt-in 조건 통과 후 DB 연결 시도까지 진행되어야 함)
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    test_file = vault_dir / "test_doc.md"
    test_file.write_text("DB 연결 실패 테스트용 파일", encoding="utf-8")

    test_project = "__test_db_fail__"
    patched_projects = dict(config_mod.PROJECTS)
    patched_projects[test_project] = {
        "vault": vault_dir,
        "cold": None,
        "done": None,
        "docs_root": None,
        "catalog": None,
        "vault_cleanup": {
            "active": True,
            "retention_days": 90,
        },
    }
    monkeypatch.setattr(config_mod, "PROJECTS", patched_projects)
    monkeypatch.setattr(vc_mod, "PROJECTS", patched_projects)

    # get_db_connection을 예외 발생 컨텍스트 매니저로 monkeypatch
    # vault_cleanup.run()은 함수 내부에서 `from loregist.config import get_db_connection`로
    # 임포트하므로 loregist.config 모듈에서 직접 패치해야 함
    class _FailCtx:
        def __enter__(self):
            raise Exception("connection refused")
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(config_mod, "get_db_connection", lambda: _FailCtx())

    with pytest.raises(SystemExit) as exc_info:
        vc_mod.run(test_project, dry_run=True)

    assert exc_info.value.code == 1, (
        f"DB 연결 실패 시 sys.exit(1)을 호출해야 함, 실제: {exc_info.value.code}"
    )

    captured = capsys.readouterr()
    assert "DB 연결 실패" in captured.err, (
        f"stderr에 'DB 연결 실패' 메시지가 포함되어야 함, 실제: {captured.err!r}"
    )

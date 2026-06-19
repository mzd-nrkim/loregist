"""
tests/test_rotate.py
rotate.py 유닛·통합 테스트

Unit (DB 불필요):
  R-1: parse_folder_date — 날짜 문자열 파싱 / 비날짜 None
  R-2: discover_rotate_targets — 임계일 초과 폴더만 반환
  R-3: discover_rotate_targets — _catalog 제외
  R-4: rotate_file — vault=None → False, 파일 무변경
  R-5: git_rm — untracked 파일 → False
  R-7: discover_done_rotate_targets — 임계일 기준 done 파일 포함/제외
  R-8: rotate_done_file — vault=None → False, 파일 무변경
  R-9: cold 키만 있는 프로젝트 → discover_done_rotate_targets 빈 리스트 (cold 비대상 불변식)
  R-10: done 경로 *.md 가 discover_embed_files 에 포함됨

Integration (pgvector 기동 전제):
  R-6: is_embedded — INSERT 후 True / 미존재 경로 False
"""

import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

import loregist.config as vector_config
from loregist.config import ROTATE_TO_VAULT_DAYS
from loregist.rotate import (
    discover_done_rotate_targets,
    discover_rotate_targets,
    git_rm,
    parse_folder_date,
    rotate_done_file,
    rotate_file,
)


# ──────────────────────────────────────────────────────────────
# R-1: parse_folder_date
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_parse_folder_date():
    """
    날짜 형식 문자열 → date 반환, 그 외 → None.
    """
    assert parse_folder_date("2026-05-08") == date(2026, 5, 8)
    assert parse_folder_date("result") is None


# ──────────────────────────────────────────────────────────────
# R-2: discover_rotate_targets — 임계일 기준 포함/제외
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_discover_rotate_targets_threshold(monkeypatch, tmp_path):
    """
    ROTATE_TO_VAULT_DAYS 초과 경과한 폴더의 .md 파일만 반환되고,
    기간 미경과·오늘 폴더는 제외된다.
    """
    docs = tmp_path / "docs"
    docs.mkdir()

    old_date = date.today() - timedelta(days=ROTATE_TO_VAULT_DAYS + 1)
    fresh_date = date.today() - timedelta(days=1)
    today_date = date.today()

    for d in (old_date, fresh_date, today_date):
        folder = docs / d.isoformat()
        folder.mkdir()
        (folder / "f.md").write_text("x" * 120)

    monkeypatch.setitem(
        vector_config.PROJECTS,
        "__t_rot__",
        {
            "docs_root": docs,
            "vault": tmp_path / "v",
            "done": None,
            "cold": None,
        },
    )

    targets = discover_rotate_targets("__t_rot__")
    target_paths = [p for p, _ in targets]

    # old 폴더 md만 포함
    assert docs / old_date.isoformat() / "f.md" in target_paths
    # fresh(1일 경과) 제외
    assert docs / fresh_date.isoformat() / "f.md" not in target_paths
    # 오늘 폴더 제외
    assert docs / today_date.isoformat() / "f.md" not in target_paths


# ──────────────────────────────────────────────────────────────
# R-3: discover_rotate_targets — _catalog 제외
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_discover_rotate_targets_excludes_catalog(monkeypatch, tmp_path):
    """
    _catalog 하위 파일은 날짜 폴더가 있어도 반환되지 않는다.
    """
    docs = tmp_path / "docs"
    docs.mkdir()

    for special_dir in ("_catalog",):
        sub = docs / special_dir / "2020-01-01"
        sub.mkdir(parents=True)
        (sub / "x.md").write_text("x" * 120)

    monkeypatch.setitem(
        vector_config.PROJECTS,
        "__t_excl__",
        {
            "docs_root": docs,
            "vault": tmp_path / "v",
            "done": None,
            "cold": None,
        },
    )

    targets = discover_rotate_targets("__t_excl__")
    assert len(targets) == 0


# ──────────────────────────────────────────────────────────────
# R-4: rotate_file — vault=None → False, 파일 무변경
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_rotate_file_vault_none_skips(monkeypatch, tmp_path):
    """
    project의 vault 경로가 None이면 rotate_file은 False를 반환하고
    원본 파일을 변경하지 않는다.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    src = docs / "some.md"
    src.write_text("hello")

    monkeypatch.setitem(
        vector_config.PROJECTS,
        "__t_none__",
        {
            "docs_root": docs,
            "vault": None,
            "done": None,
            "cold": None,
        },
    )

    result = rotate_file(src, "__t_none__")
    assert result is False
    assert src.exists()


# ──────────────────────────────────────────────────────────────
# R-5: git_rm — untracked 파일 → False
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_git_rm_untracked_returns_false(tmp_path):
    """
    git 저장소에 추적되지 않은 파일을 git_rm에 넘기면 False를 반환한다.
    """
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "T"],
        check=True,
        capture_output=True,
    )

    a = tmp_path / "a.md"
    a.write_text("x")

    assert git_rm(tmp_path, a) is False


# ──────────────────────────────────────────────────────────────
# R-6: is_embedded roundtrip (integration)
# ──────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_is_embedded_roundtrip(real_db):
    """
    doc_originals에 INSERT한 경로는 is_embedded가 True를 반환하고,
    존재하지 않는 경로는 False를 반환한다.
    teardown: 삽입한 레코드 DELETE.
    """
    from loregist.config import get_db_connection
    from loregist.rotate import is_embedded

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO doc_originals(project, source_path, source_kind, full_text, file_hash)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (real_db, "/tmp/x.md", "md", "x", "h"),
        )
        conn.commit()

        assert is_embedded(conn, real_db, Path("/tmp/x.md")) is True
        assert is_embedded(conn, real_db, Path("/tmp/nonexistent.md")) is False

        # teardown
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM doc_originals WHERE project = %s AND source_path = '/tmp/x.md'",
            (real_db,),
        )
        conn.commit()


# ──────────────────────────────────────────────────────────────
# R-7: discover_done_rotate_targets — 임계일 기준 done 파일 포함/제외
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_discover_done_rotate_targets_threshold(monkeypatch, tmp_path):
    """파일명 날짜 기준 7일 초과 파일만 반환, 미경과·날짜없는 파일 제외."""
    done_dir = tmp_path / "done"
    done_dir.mkdir()

    old_name = f"{(date.today() - timedelta(days=ROTATE_TO_VAULT_DAYS + 1)).strftime('%Y-%m-%d')}.plan.md"
    fresh_name = f"{(date.today() - timedelta(days=1)).strftime('%Y-%m-%d')}.plan.md"

    (done_dir / old_name).write_text("x" * 120)
    (done_dir / fresh_name).write_text("x" * 120)
    (done_dir / "README.md").write_text("날짜 없는 파일")

    monkeypatch.setitem(
        vector_config.PROJECTS,
        "__t_done__",
        {"done": done_dir, "vault": tmp_path / "v", "docs_root": None, "cold": None},
    )

    targets = discover_done_rotate_targets("__t_done__")
    paths = [p for p, _ in targets]

    assert done_dir / old_name in paths
    assert done_dir / fresh_name not in paths
    assert done_dir / "README.md" not in paths


# ──────────────────────────────────────────────────────────────
# R-8: rotate_done_file — vault=None → False, 파일 무변경
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_rotate_done_file_vault_none_skips(monkeypatch, tmp_path):
    """vault=None 이면 False 반환, 파일 무변경."""
    done_dir = tmp_path / "done"
    done_dir.mkdir()
    src = done_dir / "2026-01-01.plan.md"
    src.write_text("내용")

    monkeypatch.setitem(
        vector_config.PROJECTS,
        "__t_dv__",
        {"done": done_dir, "vault": None, "docs_root": None, "cold": None},
    )

    result = rotate_done_file(src, "__t_dv__")
    assert result is False
    assert src.exists()


# ──────────────────────────────────────────────────────────────
# R-9: cold 키만 있는 프로젝트 → discover_done_rotate_targets 빈 리스트
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cold_not_rotate_target(monkeypatch, tmp_path):
    """
    cold 키만 있고 done 키가 없는 프로젝트에서
    discover_done_rotate_targets 는 빈 리스트를 반환한다 — cold는 rotate 비대상 불변식.
    """
    cold_dir = tmp_path / "cold"
    cold_dir.mkdir()

    old_name = f"{(date.today() - timedelta(days=ROTATE_TO_VAULT_DAYS + 1)).strftime('%Y-%m-%d')}.plan.md"
    (cold_dir / old_name).write_text("x" * 120)

    monkeypatch.setitem(
        vector_config.PROJECTS,
        "__t_cold_only__",
        {"cold": cold_dir, "vault": tmp_path / "v", "docs_root": None, "done": None},
    )

    targets = discover_done_rotate_targets("__t_cold_only__")
    assert targets == [], "cold 경로 파일은 rotate 대상이 아님"


# ──────────────────────────────────────────────────────────────
# R-10: done 경로 *.md 가 discover_embed_files 에 포함됨
# ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_done_included_in_embed_files(monkeypatch, tmp_path):
    """
    done 경로의 *.md 파일이 discover_embed_files 결과에 포함된다.
    """
    from loregist.embed import discover_embed_files

    done_dir = tmp_path / "done"
    done_dir.mkdir()
    md = done_dir / "2026-01-01.plan.md"
    md.write_text("내용")

    monkeypatch.setitem(
        vector_config.PROJECTS,
        "__t_embed_done__",
        {"done": done_dir, "vault": None, "docs_root": None, "cold": None},
    )

    files = discover_embed_files("__t_embed_done__")
    paths = [Path(p) for p, _ in files]
    assert md in paths, "done 경로 md 가 embed 대상에 포함되어야 함"

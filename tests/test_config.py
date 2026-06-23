"""
tests/test_config.py
T2 — config 유닛 테스트 (실DB 불필요)

T2-1: infer_project — explicit 우선 / loregist 경로 매칭 / LOREGIST_CWD 환경변수 / 미등록→ValueError
T2-2: discover_embed_files — 미존재 경로 project 슬롯 → 빈 리스트 반환
"""

import pytest
from pathlib import Path
from loregist.config import infer_project, PROJECTS, WORKSPACE
import loregist.config as vector_config


# ──────────────────────────────────────────────────────────────
# T2-1: infer_project
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_infer_project_explicit_takes_priority():
    """
    explicit 인수가 지정되면 cwd·환경변수를 무시하고 그 값을 그대로 반환한다.
    """
    result = infer_project(explicit="loregist")
    assert result == "loregist"


@pytest.mark.unit
def test_infer_project_explicit_arbitrary_value():
    """
    explicit은 PROJECTS 등록 여부와 무관하게 그대로 반환된다.
    """
    result = infer_project(explicit="arbitrary_project_name")
    assert result == "arbitrary_project_name"


@pytest.mark.unit
def test_infer_project_from_cwd_loregist(monkeypatch, tmp_path):
    """
    cwd가 loregist docs_root 하위이면
    docs_root longest-match에 의해 'loregist'를 반환한다.
    """
    loregist_docs_root = tmp_path / "loregist" / "dev"
    loregist_docs_root.mkdir(parents=True)
    loregist_cwd = str(loregist_docs_root / "2026-06-16")

    fake_cfg = {
        "vault": None,
        "archive": None,
        "docs_root": loregist_docs_root,
    }
    monkeypatch.setitem(vector_config.PROJECTS, "loregist", fake_cfg)

    result = infer_project(cwd=loregist_cwd)
    assert result == "loregist"


@pytest.mark.unit
def test_infer_project_from_env_var(monkeypatch, tmp_path):
    """
    cwd 미지정 시 LOREGIST_CWD 환경변수에서 경로를 읽어 project를 추론한다.
    """
    loregist_docs_root = tmp_path / "loregist" / "dev"
    loregist_docs_root.mkdir(parents=True)
    loregist_path = str(loregist_docs_root / "2026-06-16")

    fake_cfg = {
        "vault": None,
        "archive": None,
        "docs_root": loregist_docs_root,
    }
    monkeypatch.setitem(vector_config.PROJECTS, "loregist", fake_cfg)
    monkeypatch.setenv("LOREGIST_CWD", loregist_path)
    result = infer_project()
    assert result == "loregist"


@pytest.mark.unit
def test_infer_project_unregistered_raises_value_error():
    """
    미등록 경로를 cwd로 전달하면 ValueError가 발생해야 한다.
    E-1: 미등록 cwd → ValueError 검증.
    """
    with pytest.raises(ValueError):
        infer_project(cwd="/some/completely/unknown/path")


# ──────────────────────────────────────────────────────────────
# T2-2: discover_embed_files
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_embed_files_empty_dirs(monkeypatch, tmp_path):
    """
    vault / archive / docs_root 경로가 모두 미존재인 가짜 project 슬롯을 주입하면
    discover_embed_files는 빈 리스트를 반환한다.
    B-7: 미존재 vault 경로 → discover 빈 리스트.

    PROJECTS는 vector_config와 vector_embed가 동일 dict 객체를 공유하므로
    monkeypatch.setitem으로 주입하면 discover_embed_files 호출에 반영된다.
    """
    from loregist.embed import discover_embed_files

    fake_project = "__test_empty_project__"
    fake_cfg = {
        "vault": tmp_path / "nonexistent_vault",
        "archive": tmp_path / "nonexistent_archive",
        "docs_root": tmp_path / "nonexistent_docs",
    }
    # 세 경로 모두 tmp_path 하위이지만 생성하지 않음 → 미존재 상태
    monkeypatch.setitem(vector_config.PROJECTS, fake_project, fake_cfg)

    result = discover_embed_files(fake_project)
    assert result == []


@pytest.mark.unit
def test_discover_embed_files_none_paths(monkeypatch, tmp_path):
    """
    S-4a: vault/docs_root가 None인 project(loregist 패턴)에서
    discover_embed_files 호출 시 AttributeError 없이 빈 리스트를 반환한다.
    """
    from loregist.embed import discover_embed_files

    fake_project = "__test_none_paths__"
    fake_cfg = {
        "vault": None,
        "archive": tmp_path / "nonexistent_archive",
        "docs_root": None,
    }
    monkeypatch.setitem(vector_config.PROJECTS, fake_project, fake_cfg)

    result = discover_embed_files(fake_project)
    assert result == []


@pytest.mark.unit
def test_discover_embed_files_empty_existing_dirs(monkeypatch, tmp_path):
    """
    vault / archive / docs_root가 존재하지만 파일이 없는 빈 디렉터리인 경우
    discover_embed_files는 빈 리스트를 반환한다.
    """
    from loregist.embed import discover_embed_files

    fake_project = "__test_empty_existing__"
    # 빈 디렉터리 생성
    vault_dir = tmp_path / "vault"
    archive_dir = tmp_path / "archive"
    docs_dir = tmp_path / "docs"
    vault_dir.mkdir()
    archive_dir.mkdir()
    docs_dir.mkdir()

    fake_cfg = {
        "vault": vault_dir,
        "archive": archive_dir,
        "docs_root": docs_dir,
    }
    monkeypatch.setitem(vector_config.PROJECTS, fake_project, fake_cfg)

    result = discover_embed_files(fake_project)
    assert result == []


# ──────────────────────────────────────────────────────────────
# T_folder: _parse_handbook 폴더 경로 처리 (Plan 3)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_parse_handbook_folder_path(tmp_path):
    """
    폴더 경로 입력 시 하위 .md 파일 전체를 반환한다.
    """
    from loregist.config import _parse_handbook

    # 임시 폴더에 .md 파일 2개 생성
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.md").write_text("b")
    (tmp_path / "c.txt").write_text("not md")  # 제외 대상

    entry = {"handbook": [{"path": str(tmp_path), "writable": False}]}
    result = _parse_handbook(entry, "test")

    paths = {r["path"] for r in result}
    assert tmp_path / "a.md" in paths
    assert tmp_path / "b.md" in paths
    assert len(result) == 2
    assert all(r["writable"] is False for r in result)


@pytest.mark.unit
def test_parse_handbook_empty_folder(tmp_path, capsys):
    """
    빈 폴더 입력 시 WARN 출력 + 빈 리스트 반환.
    """
    from loregist.config import _parse_handbook

    entry = {"handbook": [{"path": str(tmp_path), "writable": False}]}
    result = _parse_handbook(entry, "test")

    assert result == []
    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "0건" in captured.err


@pytest.mark.unit
def test_parse_handbook_glob_unchanged(tmp_path, monkeypatch):
    """
    기존 glob 패턴(*.md)이 여전히 정상 동작한다 (회귀).
    tmp_path 기반 격리 — 레포 레이아웃에 의존하지 않는다.
    """
    import loregist.config as _cfg
    from loregist.config import _parse_handbook

    # tmp_path 하위에 .md 파일 2개 생성
    (tmp_path / "a.md").write_text("x")
    (tmp_path / "b.md").write_text("y")

    # WORKSPACE를 tmp_path로 교체 (monkeypatch가 자동 복원)
    monkeypatch.setattr(_cfg, "WORKSPACE", tmp_path)

    # tmp_path 기준 상대 glob 패턴
    entry = {"handbook": [{"path": "*.md", "writable": False}]}
    result = _parse_handbook(entry, "test")

    # 결과가 비어 있지 않고 모두 .md 경로여야 한다
    assert len(result) >= 1
    assert all(str(r["path"]).endswith(".md") for r in result)


@pytest.mark.unit
def test_parse_handbook_single_file_unchanged(tmp_path):
    """
    단일 파일 경로가 여전히 정상 동작한다 (회귀).
    """
    from loregist.config import _parse_handbook

    f = tmp_path / "note.md"
    f.write_text("hello")

    entry = {"handbook": [{"path": str(f), "writable": True}]}
    result = _parse_handbook(entry, "test")

    assert len(result) == 1
    assert result[0]["path"] == f
    assert result[0]["writable"] is True

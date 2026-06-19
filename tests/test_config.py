"""
tests/test_config.py
T2 — config 유닛 테스트 (실DB 불필요)

T2-1: infer_project — explicit 우선 / docs_root 경로 매칭 / LOREGIST_CWD 환경변수 / 미등록→ValueError
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
    result = infer_project(explicit="project-a")
    assert result == "project-a"


@pytest.mark.unit
def test_infer_project_explicit_arbitrary_value():
    """
    explicit은 PROJECTS 등록 여부와 무관하게 그대로 반환된다.
    """
    result = infer_project(explicit="arbitrary_project_name")
    assert result == "arbitrary_project_name"


@pytest.mark.unit
def test_infer_project_from_cwd(monkeypatch, tmp_path):
    """
    cwd가 project-a의 docs_root 하위이면
    docs_root longest-match에 의해 'project-a'를 반환한다.
    """
    docs_root = tmp_path / "project-a" / "dev"
    docs_root.mkdir(parents=True)
    cwd = str(docs_root / "2026-06-16")

    fake_projects = dict(vector_config.PROJECTS)
    fake_projects["project-a"] = {
        "docs_root": docs_root,
        "vault": None,
        "cold": None,
        "done": None,
        "catalog": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setattr(vector_config, "PROJECTS", fake_projects)

    result = infer_project(cwd=cwd)
    assert result == "project-a"


@pytest.mark.unit
def test_infer_project_from_env_var(monkeypatch, tmp_path):
    """
    cwd 미지정 시 LOREGIST_CWD 환경변수에서 경로를 읽어 project를 추론한다.
    """
    docs_root = tmp_path / "project-a" / "dev"
    docs_root.mkdir(parents=True)
    cwd_path = str(docs_root / "2026-06-16")

    fake_projects = dict(vector_config.PROJECTS)
    fake_projects["project-a"] = {
        "docs_root": docs_root,
        "vault": None,
        "cold": None,
        "done": None,
        "catalog": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setattr(vector_config, "PROJECTS", fake_projects)
    monkeypatch.setenv("LOREGIST_CWD", cwd_path)

    result = infer_project()
    assert result == "project-a"


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

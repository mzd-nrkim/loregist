"""
tests/test_load_projects.py
load_projects() 로더 단위 테스트 (DB 불필요)

B-4:
  - 상대경로 항목 → WORKSPACE 기준 절대 Path resolve
  - 누락 키(vault 생략) → None
  - 절대경로 / ~ → expanduser 결과 (WORKSPACE 미접두)
  - 부재 파일 → FileNotFoundError
  - [projects] 없는 빈 파일 → {}
"""

import pytest
from pathlib import Path
from loregist.config import load_projects, WORKSPACE


# ──────────────────────────────────────────────────────────────
# 헬퍼: tmp_path에 .toml 작성
# ──────────────────────────────────────────────────────────────

def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "projects.toml"
    p.write_text(content, encoding="utf-8")
    return p


# ──────────────────────────────────────────────────────────────
# B-4-1: 상대경로 → WORKSPACE 기준 절대 Path
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_load_projects_relative_paths(tmp_path):
    """
    상대경로(tools/foo/bar)는 WORKSPACE / "tools/foo/bar" 형태의 절대 Path로 resolve된다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/personal-work/projects/test/dev"
vault     = "logvault/test"
cold      = "logvault/test/cold"
""")
    result = load_projects(toml_path)
    proj = result["test-proj"]
    assert proj["docs_root"] == WORKSPACE / "tools/personal-work/projects/test/dev"
    assert proj["vault"] == WORKSPACE / "logvault/test"
    assert proj["cold"] == WORKSPACE / "logvault/test/cold"
    # 결과는 Path 객체
    assert isinstance(proj["docs_root"], Path)


# ──────────────────────────────────────────────────────────────
# B-4-2: 누락 키 → None
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_load_projects_missing_keys_are_none(tmp_path):
    """
    vault/done/cold/docs_root 키가 없으면 해당 값은 None이다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.loregist]
done = "loregist_private/plans/done"
""")
    result = load_projects(toml_path)
    proj = result["loregist"]
    assert proj["vault"] is None
    assert proj["docs_root"] is None
    assert proj["cold"] is None
    assert proj["done"] == WORKSPACE / "loregist_private/plans/done"


# ──────────────────────────────────────────────────────────────
# B-4-3: 절대경로 → expanduser 결과 (WORKSPACE 미접두)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_load_projects_absolute_path_no_workspace_prefix(tmp_path):
    """
    절대경로 값은 WORKSPACE를 앞에 붙이지 않고 그대로 Path로 반환한다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.abs-proj]
docs_root = "/tmp/absolute/path"
""")
    result = load_projects(toml_path)
    assert result["abs-proj"]["docs_root"] == Path("/tmp/absolute/path")
    # WORKSPACE가 접두로 붙지 않는지 확인
    assert not str(result["abs-proj"]["docs_root"]).startswith(str(WORKSPACE))


@pytest.mark.unit
def test_load_projects_tilde_path_expands(tmp_path):
    """
    ~ 경로는 expanduser()로 펼쳐지고 WORKSPACE를 앞에 붙이지 않는다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.home-proj]
docs_root = "~/some/path"
""")
    result = load_projects(toml_path)
    resolved = result["home-proj"]["docs_root"]
    assert not str(resolved).startswith("~")
    assert resolved == Path("~/some/path").expanduser()


# ──────────────────────────────────────────────────────────────
# B-4-4: 부재 파일 → FileNotFoundError
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_load_projects_missing_file_raises(tmp_path):
    """
    projects.toml이 존재하지 않으면 FileNotFoundError를 발생시킨다.
    """
    nonexistent = tmp_path / "no_such_file.toml"
    with pytest.raises(FileNotFoundError):
        load_projects(nonexistent)


# ──────────────────────────────────────────────────────────────
# B-4-5: [projects] 섹션 없는 빈 파일 → {} 반환
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_load_projects_empty_toml_returns_empty_dict(tmp_path):
    """
    [projects] 섹션이 없는 빈 toml 파일은 빈 dict를 반환한다.
    """
    toml_path = _write_toml(tmp_path, "# 빈 파일\n")
    result = load_projects(toml_path)
    assert result == {}


@pytest.mark.unit
def test_load_projects_no_projects_section_returns_empty_dict(tmp_path):
    """
    [other] 섹션만 있고 [projects] 없으면 빈 dict를 반환한다.
    """
    toml_path = _write_toml(tmp_path, """
[other]
key = "value"
""")
    result = load_projects(toml_path)
    assert result == {}

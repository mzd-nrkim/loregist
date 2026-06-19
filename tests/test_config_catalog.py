"""
tests/test_config_catalog.py
catalog / vault_cleanup opt-in 파싱 단위 테스트 (DB 불필요)

TC 항목:
  - load_projects가 catalog 키 3케이스(true/문자열/생략)를 정확히 해석하는지
  - docs_root 없는 블록 + catalog=true → 경고 + None
  - vault_cleanup 키 3케이스(true/정수/생략) 해석
  - vault_cleanup=true → VAULT_RETENTION_DAYS(90) 적용, 정수 → override
"""

import pytest
from pathlib import Path
from loregist.config import load_projects, WORKSPACE, VAULT_RETENTION_DAYS


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "projects.toml"
    p.write_text(content, encoding="utf-8")
    return p


# ──────────────────────────────────────────────────────────────
# A-opt: catalog 키 3케이스
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_catalog_true_resolves_to_docs_root_slash_catalog(tmp_path):
    """
    catalog = true → {docs_root}/_catalog 경로로 resolve 된다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/personal-work/projects/test/dev"
catalog   = true
""")
    result = load_projects(toml_path)
    expected = WORKSPACE / "tools/personal-work/projects/test/dev" / "_catalog"
    assert result["test-proj"]["catalog"] == expected


@pytest.mark.unit
def test_catalog_string_uses_path_as_is(tmp_path):
    """
    catalog = "경로" → _resolve_path(경로) 결과를 그대로 사용한다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/personal-work/projects/test/dev"
catalog   = "tools/personal-work/projects/test/_catalog"
""")
    result = load_projects(toml_path)
    expected = WORKSPACE / "tools/personal-work/projects/test/_catalog"
    assert result["test-proj"]["catalog"] == expected


@pytest.mark.unit
def test_catalog_omitted_is_none(tmp_path):
    """
    catalog 키 생략 → None (비대상).
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/personal-work/projects/test/dev"
vault     = "logvault/test"
""")
    result = load_projects(toml_path)
    assert result["test-proj"]["catalog"] is None


@pytest.mark.unit
def test_catalog_true_without_docs_root_warns_and_returns_none(tmp_path, capsys):
    """
    docs_root 없는 블록 + catalog=true → 경고 출력 + None 반환.
    """
    toml_path = _write_toml(tmp_path, """
[projects.no-docs-root]
vault   = "logvault/no-docs"
catalog = true
""")
    result = load_projects(toml_path)
    assert result["no-docs-root"]["catalog"] is None

    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "no-docs-root" in captured.err
    assert "docs_root" in captured.err


@pytest.mark.unit
def test_catalog_false_is_none(tmp_path):
    """
    catalog = false → None (비대상, bool false 처리).
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/personal-work/projects/test/dev"
catalog   = false
""")
    result = load_projects(toml_path)
    assert result["test-proj"]["catalog"] is None


# ──────────────────────────────────────────────────────────────
# E-opt: vault_cleanup 키 3케이스
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_vault_cleanup_true_activates_with_default_retention(tmp_path):
    """
    vault_cleanup = true → 활성(active=True) + VAULT_RETENTION_DAYS(90일) 적용.
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
vault         = "logvault/test"
vault_cleanup = true
""")
    result = load_projects(toml_path)
    vc = result["test-proj"]["vault_cleanup"]
    assert vc["active"] is True
    assert vc["retention_days"] == VAULT_RETENTION_DAYS
    assert vc["retention_days"] == 90


@pytest.mark.unit
def test_vault_cleanup_integer_overrides_retention(tmp_path):
    """
    vault_cleanup = 180 → 활성(active=True) + 보존일 180 override.
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
vault         = "logvault/test"
vault_cleanup = 180
""")
    result = load_projects(toml_path)
    vc = result["test-proj"]["vault_cleanup"]
    assert vc["active"] is True
    assert vc["retention_days"] == 180


@pytest.mark.unit
def test_vault_cleanup_omitted_is_inactive(tmp_path):
    """
    vault_cleanup 키 생략 → 비활성(active=False).
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
vault = "logvault/test"
""")
    result = load_projects(toml_path)
    vc = result["test-proj"]["vault_cleanup"]
    assert vc["active"] is False
    assert vc["retention_days"] is None


@pytest.mark.unit
def test_vault_cleanup_false_is_inactive(tmp_path):
    """
    vault_cleanup = false → 비활성(active=False).
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
vault         = "logvault/test"
vault_cleanup = false
""")
    result = load_projects(toml_path)
    vc = result["test-proj"]["vault_cleanup"]
    assert vc["active"] is False


# ──────────────────────────────────────────────────────────────
# E-3: VAULT_RETENTION_DAYS fallback 상수 확인
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_vault_retention_days_constant_is_90():
    """
    VAULT_RETENTION_DAYS 상수가 90임을 확인한다.
    """
    assert VAULT_RETENTION_DAYS == 90


@pytest.mark.unit
def test_vault_cleanup_true_uses_vault_retention_days_fallback(tmp_path):
    """
    vault_cleanup=true → retention_days가 VAULT_RETENTION_DAYS와 동일한지 확인.
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
vault         = "logvault/test"
vault_cleanup = true
""")
    result = load_projects(toml_path)
    vc = result["test-proj"]["vault_cleanup"]
    assert vc["retention_days"] == VAULT_RETENTION_DAYS


@pytest.mark.unit
def test_vault_cleanup_integer_overrides_vault_retention_days(tmp_path):
    """
    vault_cleanup=<정수> → VAULT_RETENTION_DAYS(90)가 아닌 해당 정수 값을 사용한다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
vault         = "logvault/test"
vault_cleanup = 30
""")
    result = load_projects(toml_path)
    vc = result["test-proj"]["vault_cleanup"]
    assert vc["retention_days"] == 30
    assert vc["retention_days"] != VAULT_RETENTION_DAYS


# ──────────────────────────────────────────────────────────────
# 복합: catalog + vault_cleanup 함께 지정
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_catalog_and_vault_cleanup_together(tmp_path):
    """
    catalog + vault_cleanup 둘 다 지정 시 각각 독립적으로 해석된다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.full-proj]
docs_root     = "tools/personal-work/projects/full/dev"
vault         = "logvault/full"
cold          = "logvault/full/cold"
catalog       = true
vault_cleanup = 180
""")
    result = load_projects(toml_path)
    proj = result["full-proj"]

    # catalog
    expected_catalog = WORKSPACE / "tools/personal-work/projects/full/dev" / "_catalog"
    assert proj["catalog"] == expected_catalog

    # vault_cleanup
    vc = proj["vault_cleanup"]
    assert vc["active"] is True
    assert vc["retention_days"] == 180

    # 기존 필드 정상 유지
    assert proj["vault"] == WORKSPACE / "logvault/full"
    assert proj["cold"] == WORKSPACE / "logvault/full/cold"

"""
tests/test_config_flags.py
auto_handbook_update / auto_catalog_update 플래그 파싱 및
decide_entry_skill 단위 테스트 (DB 불필요)

TC 항목:
  - 미설정 프로젝트 → 두 플래그 모두 False (Existence / 하위호환)
  - auto_handbook_update = true, auto_catalog_update = false 명시 → 정확히 반영
  - 두 플래그 각각 true/false 명시값 케이스
  - 잘못된 타입(문자열) → False로 안전 처리(WARN 출력)
  - decide_entry_skill 4조합 → 목표 표대로 반환값 확인 (Cross-check)
  - dump_projects() 출력 JSON에 두 플래그 필드가 포함되는지 검증
"""

import json
import sys
import pytest
from pathlib import Path

import loregist.config as config_mod
from loregist.config import load_projects, decide_entry_skill


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "projects.toml"
    p.write_text(content, encoding="utf-8")
    return p


# ──────────────────────────────────────────────────────────────
# A. 플래그 파싱 — 미설정 시 기본값 False
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_flags_default_false_when_keys_omitted(tmp_path):
    """키를 생략하면 두 플래그 모두 False로 파싱된다 (Existence / 하위호환)."""
    toml_path = _write_toml(tmp_path, """
[projects.alpha]
docs_root = "workspace/alpha/dev"
vault     = "logvault/alpha"
""")
    result = load_projects(toml_path)
    assert result["alpha"]["auto_handbook_update"] is False
    assert result["alpha"]["auto_catalog_update"] is False


# ──────────────────────────────────────────────────────────────
# B. 플래그 파싱 — 명시값 반영
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_true_catalog_false_explicit(tmp_path):
    """auto_handbook_update = true, auto_catalog_update = false 명시 → 정확히 반영."""
    toml_path = _write_toml(tmp_path, """
[projects.beta]
docs_root              = "workspace/beta/dev"
auto_handbook_update   = true
auto_catalog_update    = false
""")
    result = load_projects(toml_path)
    assert result["beta"]["auto_handbook_update"] is True
    assert result["beta"]["auto_catalog_update"] is False


@pytest.mark.unit
def test_handbook_false_catalog_true_explicit(tmp_path):
    """auto_handbook_update = false, auto_catalog_update = true 명시 → 정확히 반영."""
    toml_path = _write_toml(tmp_path, """
[projects.gamma]
docs_root              = "workspace/gamma/dev"
auto_handbook_update   = false
auto_catalog_update    = true
""")
    result = load_projects(toml_path)
    assert result["gamma"]["auto_handbook_update"] is False
    assert result["gamma"]["auto_catalog_update"] is True


@pytest.mark.unit
def test_both_flags_true_explicit(tmp_path):
    """두 플래그 모두 true 명시 → 둘 다 True."""
    toml_path = _write_toml(tmp_path, """
[projects.delta]
docs_root              = "workspace/delta/dev"
auto_handbook_update   = true
auto_catalog_update    = true
""")
    result = load_projects(toml_path)
    assert result["delta"]["auto_handbook_update"] is True
    assert result["delta"]["auto_catalog_update"] is True


@pytest.mark.unit
def test_both_flags_false_explicit(tmp_path):
    """두 플래그 모두 false 명시 → 둘 다 False."""
    toml_path = _write_toml(tmp_path, """
[projects.epsilon]
docs_root              = "workspace/epsilon/dev"
auto_handbook_update   = false
auto_catalog_update    = false
""")
    result = load_projects(toml_path)
    assert result["epsilon"]["auto_handbook_update"] is False
    assert result["epsilon"]["auto_catalog_update"] is False


# ──────────────────────────────────────────────────────────────
# C. 잘못된 타입 → WARN 후 False (안전 처리)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_invalid_type_string_falls_back_to_false(tmp_path, capsys):
    """문자열 값은 bool이 아니므로 WARN을 출력하고 False로 안전 처리된다."""
    toml_path = _write_toml(tmp_path, """
[projects.zeta]
docs_root              = "workspace/zeta/dev"
auto_handbook_update   = "yes"
auto_catalog_update    = "true"
""")
    result = load_projects(toml_path)
    assert result["zeta"]["auto_handbook_update"] is False
    assert result["zeta"]["auto_catalog_update"] is False

    # WARN이 stderr로 출력되었는지 확인
    captured = capsys.readouterr()
    assert "[WARN]" in captured.err
    assert "auto_handbook_update" in captured.err
    assert "auto_catalog_update" in captured.err


@pytest.mark.unit
def test_invalid_type_integer_falls_back_to_false(tmp_path, capsys):
    """정수 값(bool이 아닌 int)은 WARN을 출력하고 False로 안전 처리된다.
    참고: TOML에서 1/0은 정수이며 bool이 아니다."""
    toml_path = _write_toml(tmp_path, """
[projects.eta]
docs_root              = "workspace/eta/dev"
auto_handbook_update   = 1
auto_catalog_update    = 0
""")
    result = load_projects(toml_path)
    assert result["eta"]["auto_handbook_update"] is False
    assert result["eta"]["auto_catalog_update"] is False

    captured = capsys.readouterr()
    assert "[WARN]" in captured.err


# ──────────────────────────────────────────────────────────────
# D. decide_entry_skill 4조합 Cross-check
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_decide_entry_skill_both_false():
    """(False, False) → None (제안 모드, 무인 진입점 없음)."""
    assert decide_entry_skill(False, False) is None


@pytest.mark.unit
def test_decide_entry_skill_catalog_only():
    """(False, True) → 'catalog-update'."""
    assert decide_entry_skill(False, True) == "catalog-update"


@pytest.mark.unit
def test_decide_entry_skill_handbook_only():
    """(True, False) → 'handbook-update'."""
    assert decide_entry_skill(True, False) == "handbook-update"


@pytest.mark.unit
def test_decide_entry_skill_both_true():
    """(True, True) → 'wiki-update'."""
    assert decide_entry_skill(True, True) == "wiki-update"


# ──────────────────────────────────────────────────────────────
# E. dump_projects() JSON에 두 플래그 필드 포함 여부 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_dump_projects_includes_flag_fields(tmp_path, monkeypatch):
    """dump_projects()가 반환하는 JSON에 auto_handbook_update·auto_catalog_update 필드가 포함된다."""
    toml_path = _write_toml(tmp_path, """
[projects.theta]
docs_root              = "workspace/theta/dev"
auto_handbook_update   = true
auto_catalog_update    = false
""")
    projects = load_projects(toml_path)
    monkeypatch.setattr(config_mod, "PROJECTS", projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    assert len(data) == 1
    proj = data[0]
    assert proj["name"] == "theta"
    assert proj["auto_handbook_update"] is True
    assert proj["auto_catalog_update"] is False


@pytest.mark.unit
def test_dump_projects_flags_default_false_in_json(tmp_path, monkeypatch):
    """플래그 미선언 프로젝트의 dump_projects() JSON 출력에서 두 필드가 false다."""
    toml_path = _write_toml(tmp_path, """
[projects.iota]
docs_root = "workspace/iota/dev"
vault     = "logvault/iota"
""")
    projects = load_projects(toml_path)
    monkeypatch.setattr(config_mod, "PROJECTS", projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "iota")
    assert proj["auto_handbook_update"] is False
    assert proj["auto_catalog_update"] is False

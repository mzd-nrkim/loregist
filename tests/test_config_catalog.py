"""
tests/test_config_catalog.py
catalog / vault_cleanup / handbook opt-in 파싱 단위 테스트 (DB 불필요)

TC 항목:
  - load_projects가 catalog 키 3케이스(true/문자열/생략)를 정확히 해석하는지
  - docs_root 없는 블록 + catalog=true → 경고 + None
  - vault_cleanup 키 3케이스(true/정수/생략) 해석
  - vault_cleanup=true → VAULT_RETENTION_DAYS(90) 적용, 정수 → override
  - handbook: list[dict] 반환(path/writable/update_when), 암묵 catalog 활성화
  - dump_projects: handbook 직렬화 구조 검증
"""

import json
import pytest
from pathlib import Path
import loregist.config as config_mod
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
    expected = WORKSPACE / "tools/personal-work/projects/test/dev" / "_wiki"
    assert result["test-proj"]["catalog"] == expected


@pytest.mark.unit
def test_catalog_string_uses_path_as_is(tmp_path):
    """
    catalog = "경로" → _resolve_path(경로) 결과를 그대로 사용한다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/personal-work/projects/test/dev"
catalog   = "tools/personal-work/projects/test/_wiki"
""")
    result = load_projects(toml_path)
    expected = WORKSPACE / "tools/personal-work/projects/test/_wiki"
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
    expected_catalog = WORKSPACE / "tools/personal-work/projects/full/dev" / "_wiki"
    assert proj["catalog"] == expected_catalog

    # vault_cleanup
    vc = proj["vault_cleanup"]
    assert vc["active"] is True
    assert vc["retention_days"] == 180

    # 기존 필드 정상 유지
    assert proj["vault"] == WORKSPACE / "logvault/full"
    assert proj["cold"] == WORKSPACE / "logvault/full/cold"


# ──────────────────────────────────────────────────────────────
# A-4: handbook 파싱 테스트
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_declared_resolves_to_path_list(tmp_path):
    """handbook 선언 → list[dict] 반환, 각 원소 path/writable/update_when 검증"""
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook = ["tools/test/etc/infra.md", "tools/test/etc/policy.md"]
""")
    result = load_projects(toml_path)
    ws = result["test-proj"]["handbook"]
    assert isinstance(ws, list)
    assert len(ws) == 2
    # 각 원소는 dict
    assert all(isinstance(item, dict) for item in ws)
    # path 값 검증 (Path 객체)
    assert ws[0]["path"] == WORKSPACE / "tools/test/etc/infra.md"
    assert ws[1]["path"] == WORKSPACE / "tools/test/etc/policy.md"
    # 문자열 항목은 writable=False, update_when=None (하위 호환)
    assert ws[0]["writable"] is False
    assert ws[0]["update_when"] is None
    assert ws[1]["writable"] is False
    assert ws[1]["update_when"] is None


@pytest.mark.unit
def test_handbook_without_catalog_warns_and_ignored(tmp_path, capsys):
    """catalog 없이 handbook만 선언 + docs_root 없음 → 경고 + catalog=None (F-2 케이스)"""
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
handbook = ["tools/test/etc/infra.md"]
""")
    result = load_projects(toml_path)
    # docs_root 없으므로 암묵 활성화 불가 → catalog=None 유지
    assert result["test-proj"]["catalog"] is None
    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "handbook" in captured.err


@pytest.mark.unit
def test_handbook_omitted_returns_empty_list(tmp_path):
    """handbook 미선언 → 빈 리스트 기본값 검증"""
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/test/dev"
catalog   = true
""")
    result = load_projects(toml_path)
    assert result["test-proj"]["handbook"] == []


@pytest.mark.unit
def test_handbook_glob_no_match_warns(tmp_path, capsys):
    """glob 패턴이 0건 매칭 → 경고 + 빈 결과 검증"""
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook  = ["tools/test/etc/nonexistent-glob-*.md"]
""")
    result = load_projects(toml_path)
    ws = result["test-proj"]["handbook"]
    assert ws == []
    captured = capsys.readouterr()
    assert "WARN" in captured.err


# ──────────────────────────────────────────────────────────────
# A-5: catalog_readme 파싱 테스트
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_catalog_readme_declared_resolves_to_path(tmp_path):
    """catalog_readme 선언 → Path resolve 검증"""
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root      = "tools/test/dev"
catalog        = true
catalog_readme = "tools/test/README.md"
""")
    result = load_projects(toml_path)
    from loregist.config import WORKSPACE
    assert result["test-proj"]["catalog_readme"] == WORKSPACE / "tools/test/README.md"


@pytest.mark.unit
def test_catalog_readme_omitted_is_none(tmp_path):
    """catalog_readme 미선언 → None"""
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root = "tools/test/dev"
catalog   = true
""")
    result = load_projects(toml_path)
    assert result["test-proj"]["catalog_readme"] is None


@pytest.mark.unit
def test_catalog_readme_without_catalog_warns_and_ignored(tmp_path, capsys):
    """catalog 없이 catalog_readme → 무시 + 경고"""
    toml_path = _write_toml(tmp_path, """
[projects.test-proj]
docs_root      = "tools/test/dev"
catalog_readme = "tools/test/README.md"
""")
    result = load_projects(toml_path)
    assert result["test-proj"]["catalog_readme"] is None
    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "catalog_readme" in captured.err


# ──────────────────────────────────────────────────────────────
# F-1: 문자열·dict 혼용 handbook
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_mixed_string_and_dict(tmp_path):
    """
    F-1: 문자열·dict 혼용 handbook 선언 → list[dict] 반환.
    문자열 원소는 writable=False/update_when=None, dict 원소는 지정값 반영.
    """
    toml_path = _write_toml(tmp_path, """
[projects.mix-proj]
docs_root = "tools/test/dev"
catalog   = true

[[projects.mix-proj.handbook]]
path        = "tools/test/handbook/custom.md"
writable    = true
update_when = "daily"

[[projects.mix-proj.handbook]]
path = "tools/test/handbook/readonly.md"
""")
    result = load_projects(toml_path)
    ws = result["mix-proj"]["handbook"]
    assert isinstance(ws, list)
    assert len(ws) == 2

    # 첫 번째: writable=True, update_when="daily"
    assert ws[0]["path"] == WORKSPACE / "tools/test/handbook/custom.md"
    assert ws[0]["writable"] is True
    assert ws[0]["update_when"] == "daily"

    # 두 번째: writable=False(기본값), update_when=None
    assert ws[1]["path"] == WORKSPACE / "tools/test/handbook/readonly.md"
    assert ws[1]["writable"] is False
    assert ws[1]["update_when"] is None


# ──────────────────────────────────────────────────────────────
# F-2: docs_root 없는 프로젝트에서 handbook만 선언 → 경고 + catalog=None
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_without_docs_root_warns_and_catalog_none(tmp_path, capsys):
    """
    F-2: catalog 키 없음 + handbook 선언 + docs_root 없음
    → 경고(stderr "WARN") + catalog is None.
    """
    toml_path = _write_toml(tmp_path, """
[projects.nodocs-proj]
vault    = "logvault/nodocs"
handbook = ["tools/test/etc/infra.md"]
""")
    result = load_projects(toml_path)
    assert result["nodocs-proj"]["catalog"] is None
    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "handbook" in captured.err


# ──────────────────────────────────────────────────────────────
# F-3: catalog 키 없이 handbook + docs_root → 암묵 활성화
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_implicit_catalog_activation(tmp_path):
    """
    F-3: catalog 키 없음 + handbook 선언 + docs_root 있음
    → catalog == {docs_root}/_catalog 로 암묵 활성화.
    """
    toml_path = _write_toml(tmp_path, """
[projects.implicit-proj]
docs_root = "tools/test/dev"
handbook  = ["tools/test/etc/infra.md"]
""")
    result = load_projects(toml_path)
    expected_catalog = WORKSPACE / "tools/test/dev" / "_wiki"
    assert result["implicit-proj"]["catalog"] == expected_catalog


# ──────────────────────────────────────────────────────────────
# F-4: 문자열 리스트 형식 → writable=False 정규화
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_string_list_all_writable_false(tmp_path):
    """
    F-4: 문자열 리스트 형식 handbook 선언 → 파싱 오류 없음 + 모든 원소 writable=False.
    """
    toml_path = _write_toml(tmp_path, """
[projects.str-list-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook = [
    "tools/test/etc/a.md",
    "tools/test/etc/b.md",
    "tools/test/etc/c.md",
]
""")
    result = load_projects(toml_path)
    ws = result["str-list-proj"]["handbook"]
    assert len(ws) == 3
    assert all(item["writable"] is False for item in ws)
    assert all(item["update_when"] is None for item in ws)
    assert all(isinstance(item["path"], Path) for item in ws)


# ──────────────────────────────────────────────────────────────
# Inverse(라운드트립): toml → dump_projects JSON → 값 일치 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_roundtrip_json(tmp_path, monkeypatch):
    """
    라운드트립: toml 파싱 → dump_projects JSON 직렬화 후
    path/writable/update_when 값이 입력과 일치.
    """
    toml_path = _write_toml(tmp_path, """
[projects.rt-proj]
docs_root = "tools/test/dev"
catalog   = true

[[projects.rt-proj.handbook]]
path        = "tools/test/handbook/alpha.md"
writable    = true
update_when = "weekly"

[[projects.rt-proj.handbook]]
path = "tools/test/handbook/beta.md"
""")
    projects = load_projects(toml_path)
    monkeypatch.setattr(config_mod, "PROJECTS", projects)
    from loregist.config import dump_projects
    raw = dump_projects(as_json=True)
    data = json.loads(raw)

    rt = next(p for p in data if p["name"] == "rt-proj")
    hb = rt["handbook"]
    assert len(hb) == 2

    # 첫 번째 항목
    assert hb[0]["path"] == str(WORKSPACE / "tools/test/handbook/alpha.md")
    assert hb[0]["writable"] is True
    assert hb[0]["update_when"] == "weekly"

    # 두 번째 항목
    assert hb[1]["path"] == str(WORKSPACE / "tools/test/handbook/beta.md")
    assert hb[1]["writable"] is False
    assert hb[1]["update_when"] is None


# ──────────────────────────────────────────────────────────────
# Cross-check: catalog 암묵 활성화 경로 == {docs_root}/_catalog
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_implicit_catalog_equals_docs_root_slash_catalog(tmp_path):
    """
    Cross-check: handbook 암묵 활성화가 산출한 catalog == {docs_root}/_catalog.
    """
    docs_root = "tools/cross/dev"
    toml_path = _write_toml(tmp_path, f"""
[projects.cross-proj]
docs_root = "{docs_root}"
handbook  = ["tools/cross/handbook/page.md"]
""")
    result = load_projects(toml_path)
    expected = WORKSPACE / docs_root / "_wiki"
    assert result["cross-proj"]["catalog"] == expected


# ──────────────────────────────────────────────────────────────
# Ordering: 입력 순서 보존
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_order_preserved(tmp_path):
    """
    Ordering: handbook 배열 입력 순서가 파싱 후 보존된다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.order-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook = [
    "tools/test/z_last.md",
    "tools/test/a_first.md",
    "tools/test/m_middle.md",
]
""")
    result = load_projects(toml_path)
    ws = result["order-proj"]["handbook"]
    assert ws[0]["path"] == WORKSPACE / "tools/test/z_last.md"
    assert ws[1]["path"] == WORKSPACE / "tools/test/a_first.md"
    assert ws[2]["path"] == WORKSPACE / "tools/test/m_middle.md"


# ──────────────────────────────────────────────────────────────
# Existence: 엣지케이스 — None/빈값/missing 모두 예외 없이 처리
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_existence_no_catalog_key_safe(tmp_path):
    """
    Existence: catalog 키 없음 + handbook 없음 + docs_root 없음 → 예외 없이 안전 처리.
    """
    toml_path = _write_toml(tmp_path, """
[projects.bare-proj]
vault = "logvault/bare"
""")
    result = load_projects(toml_path)
    assert result["bare-proj"]["catalog"] is None
    assert result["bare-proj"]["handbook"] == []


@pytest.mark.unit
def test_handbook_existence_update_when_none_safe(tmp_path):
    """
    Existence: update_when 없는 dict 항목 → update_when=None 안전 처리, 예외 없음.
    """
    toml_path = _write_toml(tmp_path, """
[projects.safe-proj]
docs_root = "tools/test/dev"
catalog   = true

[[projects.safe-proj.handbook]]
path = "tools/test/handbook/no_when.md"
""")
    result = load_projects(toml_path)
    ws = result["safe-proj"]["handbook"]
    assert len(ws) == 1
    assert ws[0]["update_when"] is None


@pytest.mark.unit
def test_handbook_existence_docs_root_none_safe(tmp_path):
    """
    Existence: docs_root None + catalog=true → catalog=None, 예외 없음.
    """
    toml_path = _write_toml(tmp_path, """
[projects.nodocs2-proj]
vault   = "logvault/nodocs2"
catalog = true
""")
    result = load_projects(toml_path)
    assert result["nodocs2-proj"]["catalog"] is None


# ──────────────────────────────────────────────────────────────
# Cardinality: 0개·1개·N개·혼용
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_cardinality_zero(tmp_path):
    """Cardinality: handbook 0개 → 빈 리스트."""
    toml_path = _write_toml(tmp_path, """
[projects.zero-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook  = []
""")
    result = load_projects(toml_path)
    assert result["zero-proj"]["handbook"] == []


@pytest.mark.unit
def test_handbook_cardinality_one(tmp_path):
    """Cardinality: handbook 1개 → 원소 1개 dict."""
    toml_path = _write_toml(tmp_path, """
[projects.one-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook  = ["tools/test/single.md"]
""")
    result = load_projects(toml_path)
    ws = result["one-proj"]["handbook"]
    assert len(ws) == 1
    assert ws[0]["path"] == WORKSPACE / "tools/test/single.md"


@pytest.mark.unit
def test_handbook_cardinality_n(tmp_path):
    """Cardinality: handbook N개 → N개 dict, 각 구조 정상."""
    entries = [f"tools/test/page{i}.md" for i in range(5)]
    hb_list = "[" + ", ".join(f'"{e}"' for e in entries) + "]"
    toml_path = _write_toml(tmp_path, f"""
[projects.n-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook  = {hb_list}
""")
    result = load_projects(toml_path)
    ws = result["n-proj"]["handbook"]
    assert len(ws) == 5
    for i, item in enumerate(ws):
        assert item["path"] == WORKSPACE / entries[i]
        assert item["writable"] is False
        assert item["update_when"] is None


@pytest.mark.unit
def test_handbook_cardinality_mixed_string_and_object(tmp_path):
    """
    Cardinality: 문자열·객체 혼용 → 두 타입 모두 정상 처리.
    TOML array-of-tables([[...]]) 형식으로 문자열 equiv dict와 완전 dict를 혼용 검증.
    (TOML 스펙상 인라인 배열과 [[...]]을 같은 키에 혼용 불가 → 모두 [[...]] 사용)
    """
    toml_path = _write_toml(tmp_path, """
[projects.mixed2-proj]
docs_root = "tools/test/dev"
catalog   = true

[[projects.mixed2-proj.handbook]]
path = "tools/test/plain.md"

[[projects.mixed2-proj.handbook]]
path     = "tools/test/obj.md"
writable = true
""")
    result = load_projects(toml_path)
    ws = result["mixed2-proj"]["handbook"]
    assert len(ws) == 2
    # 첫 번째: writable 기본값 False
    assert ws[0]["path"] == WORKSPACE / "tools/test/plain.md"
    assert ws[0]["writable"] is False
    assert ws[0]["update_when"] is None
    # 두 번째: writable=True 지정값 반영
    assert ws[1]["path"] == WORKSPACE / "tools/test/obj.md"
    assert ws[1]["writable"] is True
    assert ws[1]["update_when"] is None


@pytest.mark.unit
def test_handbook_cardinality_all_dict(tmp_path):
    """Cardinality: 모두 dict 형식 → writable/update_when 각각 반영."""
    toml_path = _write_toml(tmp_path, """
[projects.alldict-proj]
docs_root = "tools/test/dev"
catalog   = true

[[projects.alldict-proj.handbook]]
path        = "tools/test/handbook/w1.md"
writable    = true
update_when = "on_commit"

[[projects.alldict-proj.handbook]]
path        = "tools/test/handbook/w2.md"
writable    = false
update_when = "daily"

[[projects.alldict-proj.handbook]]
path = "tools/test/handbook/w3.md"
""")
    result = load_projects(toml_path)
    ws = result["alldict-proj"]["handbook"]
    assert len(ws) == 3
    assert ws[0]["writable"] is True
    assert ws[0]["update_when"] == "on_commit"
    assert ws[1]["writable"] is False
    assert ws[1]["update_when"] == "daily"
    assert ws[2]["writable"] is False
    assert ws[2]["update_when"] is None


# ──────────────────────────────────────────────────────────────
# Conformance: dump_projects JSON 각 원소의 3키 보유 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_dump_projects_handbook_conformance(tmp_path, monkeypatch):
    """
    Conformance: dump_projects JSON의 handbook 각 원소가
    path/writable/update_when 3키를 가진다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.conf-proj]
docs_root = "tools/test/dev"
catalog   = true

[[projects.conf-proj.handbook]]
path        = "tools/test/handbook/page.md"
writable    = true
update_when = "weekly"

[[projects.conf-proj.handbook]]
path = "tools/test/handbook/page2.md"
""")
    projects = load_projects(toml_path)
    monkeypatch.setattr(config_mod, "PROJECTS", projects)
    from loregist.config import dump_projects
    raw = dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "conf-proj")
    for item in proj["handbook"]:
        assert set(item.keys()) >= {"path", "writable", "update_when"}


# ──────────────────────────────────────────────────────────────
# G-1: 'handbook' 키 파싱 단위 케이스
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_key_resolves_to_path_list(tmp_path):
    """
    G-1: toml에서 'handbook = [...]' 키 선언 시 load_projects가
    list[dict](path/writable/update_when) 정상 반환.
    PROJECTS dict 내부 필드는 'handbook' 키다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.handbook-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook = ["tools/test/etc/infra.md", "tools/test/etc/policy.md"]
""")
    result = load_projects(toml_path)
    ws = result["handbook-proj"]["handbook"]
    assert isinstance(ws, list)
    assert len(ws) == 2
    assert all(isinstance(item, dict) for item in ws)
    assert ws[0]["path"] == WORKSPACE / "tools/test/etc/infra.md"
    assert ws[1]["path"] == WORKSPACE / "tools/test/etc/policy.md"
    assert ws[0]["writable"] is False
    assert ws[0]["update_when"] is None
    assert ws[1]["writable"] is False
    assert ws[1]["update_when"] is None


@pytest.mark.unit
def test_handbook_key_dict_entries(tmp_path):
    """
    G-1: 'handbook' 키에 dict 항목 선언 시 writable/update_when 반영.
    """
    toml_path = _write_toml(tmp_path, """
[projects.handbook-dict-proj]
docs_root = "tools/test/dev"
catalog   = true

[[projects.handbook-dict-proj.handbook]]
path        = "tools/test/handbook/custom.md"
writable    = true
update_when = "daily"

[[projects.handbook-dict-proj.handbook]]
path = "tools/test/handbook/readonly.md"
""")
    result = load_projects(toml_path)
    ws = result["handbook-dict-proj"]["handbook"]
    assert len(ws) == 2
    assert ws[0]["path"] == WORKSPACE / "tools/test/handbook/custom.md"
    assert ws[0]["writable"] is True
    assert ws[0]["update_when"] == "daily"
    assert ws[1]["path"] == WORKSPACE / "tools/test/handbook/readonly.md"
    assert ws[1]["writable"] is False
    assert ws[1]["update_when"] is None


# ──────────────────────────────────────────────────────────────
# G-4: dump_projects 출력 키 검증 — 'handbook' 있고 'wiki'/'wiki_sources' 없음
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_dump_projects_output_key_is_handbook_not_wiki(tmp_path, monkeypatch):
    """
    G-4: dump_projects() 출력 JSON의 최상위 키에 'handbook'가 있고
    'wiki'/'wiki_sources'는 없음을 검증.
    """
    toml_path = _write_toml(tmp_path, """
[projects.key-check-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook  = ["tools/test/handbook/page.md"]
""")
    projects = load_projects(toml_path)
    monkeypatch.setattr(config_mod, "PROJECTS", projects)
    from loregist.config import dump_projects
    raw = dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "key-check-proj")
    assert "handbook" in proj, f"dump_projects 출력에 'handbook' 키가 있어야 함, 실제 키: {list(proj.keys())}"
    assert "wiki" not in proj, f"dump_projects 출력에 'wiki' 키가 없어야 함"
    assert "wiki_sources" not in proj, f"dump_projects 출력에 'wiki_sources' 키가 없어야 함"


@pytest.mark.unit
def test_dump_projects_handbook_items_have_required_keys(tmp_path, monkeypatch):
    """
    G-4: dump_projects 출력 JSON의 'handbook' 각 원소가
    path/writable/update_when 3키를 가진다.
    """
    toml_path = _write_toml(tmp_path, """
[projects.handbook-keys-proj]
docs_root = "tools/test/dev"
catalog   = true

[[projects.handbook-keys-proj.handbook]]
path        = "tools/test/handbook/page.md"
writable    = true
update_when = "weekly"

[[projects.handbook-keys-proj.handbook]]
path = "tools/test/handbook/page2.md"
""")
    projects = load_projects(toml_path)
    monkeypatch.setattr(config_mod, "PROJECTS", projects)
    from loregist.config import dump_projects
    raw = dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "handbook-keys-proj")
    for item in proj["handbook"]:
        assert set(item.keys()) >= {"path", "writable", "update_when"}


# ──────────────────────────────────────────────────────────────
# G-5: 문자열 리스트 형식 — 'handbook' 키로 동일 동작
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_string_list_all_writable_false_v2(tmp_path):
    """
    G-5: 'handbook' 키에 문자열 리스트 형식 선언 시 파싱 오류 없음 +
    모든 원소 writable=False.
    """
    toml_path = _write_toml(tmp_path, """
[projects.handbook-str-list-proj]
docs_root = "tools/test/dev"
catalog   = true
handbook = [
    "tools/test/etc/a.md",
    "tools/test/etc/b.md",
    "tools/test/etc/c.md",
]
""")
    result = load_projects(toml_path)
    ws = result["handbook-str-list-proj"]["handbook"]
    assert len(ws) == 3
    assert all(item["writable"] is False for item in ws)
    assert all(item["update_when"] is None for item in ws)
    assert all(isinstance(item["path"], Path) for item in ws)


@pytest.mark.unit
def test_handbook_key_omitted_returns_empty_list(tmp_path):
    """
    G-5: 'handbook' 미선언 → 'handbook' 내부 필드가 빈 리스트 기본값.
    """
    toml_path = _write_toml(tmp_path, """
[projects.no-handbook-proj]
docs_root = "tools/test/dev"
catalog   = true
""")
    result = load_projects(toml_path)
    assert result["no-handbook-proj"]["handbook"] == []

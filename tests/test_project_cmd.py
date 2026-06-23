"""
tests/test_project_cmd.py
G-2: project_cmd.py 단위 테스트 — list/current 출력 무손실, 알 수 없는 서브커맨드 exit 2

모든 테스트는 @pytest.mark.unit.
외부 의존성 없음 — monkeypatch로 config.PROJECTS 및 infer_project 격리.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ──────────────────────────────────────────────────────────────
# 헬퍼: 테스트용 PROJECTS 딕셔너리
# ──────────────────────────────────────────────────────────────

def _make_fake_projects():
    """테스트용 PROJECTS 딕셔너리 반환."""
    return {
        "proj-a": {
            "docs_root": Path("/fake/workspace/proj-a/dev"),
            "vault": Path("/fake/workspace/logvault/proj-a"),
            "cold": Path("/fake/workspace/logvault/proj-a/cold"),
            "done": None,
            "catalog": None,
            "vault_cleanup": {"active": False, "retention_days": None},
            "handbook": [],
            "catalog_readme": None,
        },
        "proj-b": {
            "docs_root": None,
            "vault": Path("/fake/workspace/logvault/proj-b"),
            "cold": None,
            "done": Path("/fake/workspace/proj-b/plans/done"),
            "catalog": None,
            "vault_cleanup": {"active": False, "retention_days": None},
            "handbook": [],
            "catalog_readme": None,
        },
    }


# ══════════════════════════════════════════════════════════════
# project list: dump_projects(as_json=True)와 동일 출력 (이관 무손실)
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_project_list_matches_dump_projects(monkeypatch, capsys):
    """Cross-check / Right: project list 출력 == config.dump_projects(as_json=True) 결과."""
    import loregist.config as config_mod
    from loregist import project_cmd

    fake_projects = _make_fake_projects()
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    # dump_projects가 참조하는 PROJECTS도 패치
    expected_json = config_mod.dump_projects(as_json=True)

    # project list 실행
    rc = project_cmd.main(["list"])
    captured = capsys.readouterr()

    assert rc == 0, f"project list는 exit 0이어야 함, 실제: {rc}"
    assert captured.out.strip() == expected_json.strip(), (
        f"project list 출력이 dump_projects(as_json=True) 결과와 일치해야 함.\n"
        f"기대:\n{expected_json}\n실제:\n{captured.out}"
    )


@pytest.mark.unit
def test_project_list_output_is_valid_json(monkeypatch, capsys):
    """Conformance: project list 출력이 유효한 JSON이어야 함."""
    import loregist.config as config_mod
    from loregist import project_cmd

    fake_projects = _make_fake_projects()
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    project_cmd.main(["list"])
    captured = capsys.readouterr()

    try:
        parsed = json.loads(captured.out)
    except json.JSONDecodeError as e:
        pytest.fail(f"project list 출력이 유효한 JSON이어야 함, 파싱 오류: {e}\n출력: {captured.out!r}")

    assert isinstance(parsed, list), f"project list JSON이 리스트여야 함, 실제: {type(parsed)}"


@pytest.mark.unit
def test_project_list_contains_all_projects(monkeypatch, capsys):
    """Right: project list 결과에 모든 프로젝트 이름 포함."""
    import loregist.config as config_mod
    from loregist import project_cmd

    fake_projects = _make_fake_projects()
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    project_cmd.main(["list"])
    captured = capsys.readouterr()

    parsed = json.loads(captured.out)
    names = {item["name"] for item in parsed}
    assert "proj-a" in names, f"proj-a가 project list에 포함되어야 함, 실제 이름들: {names}"
    assert "proj-b" in names, f"proj-b가 project list에 포함되어야 함, 실제 이름들: {names}"


@pytest.mark.unit
def test_project_list_empty_projects(monkeypatch, capsys):
    """Cardinality: PROJECTS가 비어 있으면 project list → 빈 JSON 배열 출력."""
    import loregist.config as config_mod
    from loregist import project_cmd

    monkeypatch.setattr(config_mod, "PROJECTS", {})

    rc = project_cmd.main(["list"])
    captured = capsys.readouterr()

    assert rc == 0
    parsed = json.loads(captured.out)
    assert parsed == [], f"빈 PROJECTS 시 [] 이어야 함, 실제: {parsed}"


# ══════════════════════════════════════════════════════════════
# project current: infer_project와 동일 동작, LOREGIST_CWD 처리, ValueError→exit1
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_project_current_returns_inferred_project(monkeypatch, capsys):
    """Right: project current 출력이 infer_project 결과와 일치."""
    import loregist.config as config_mod
    from loregist import project_cmd
    import os

    fake_projects = _make_fake_projects()
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    # LOREGIST_CWD를 proj-a docs_root 아래로 설정
    monkeypatch.setenv("LOREGIST_CWD", "/fake/workspace/proj-a/dev")

    # infer_project는 실제 PROJECTS를 보므로, 직접 패치
    monkeypatch.setattr(config_mod, "infer_project", lambda cwd=None, explicit=None: "proj-a")

    rc = project_cmd.main(["current"])
    captured = capsys.readouterr()

    assert rc == 0, f"project current는 exit 0이어야 함, 실제: {rc}"
    assert captured.out.strip() == "proj-a", (
        f"project current 출력이 'proj-a'여야 함, 실제: {captured.out!r}"
    )


@pytest.mark.unit
def test_project_current_uses_loregist_cwd_env(monkeypatch, capsys):
    """Right: LOREGIST_CWD 환경변수가 있으면 그 값을 cwd로 사용."""
    import loregist.config as config_mod
    from loregist import project_cmd

    captured_cwd = []

    def fake_infer_project(cwd=None, explicit=None):
        captured_cwd.append(cwd)
        return "proj-a"

    monkeypatch.setattr(config_mod, "infer_project", fake_infer_project)
    monkeypatch.setenv("LOREGIST_CWD", "/some/special/cwd")

    project_cmd.main(["current"])

    assert captured_cwd, "infer_project가 호출되어야 함"
    # project_cmd._cmd_current는 os.environ.get("LOREGIST_CWD", os.getcwd()) 를 cwd로 넘김
    # → /some/special/cwd가 infer_project에 전달되어야 함
    assert captured_cwd[0] == "/some/special/cwd", (
        f"LOREGIST_CWD 값이 infer_project cwd로 전달되어야 함, 실제: {captured_cwd[0]!r}"
    )


@pytest.mark.unit
def test_project_current_value_error_exits_1(monkeypatch, capsys):
    """Error: infer_project가 ValueError → stderr 메시지 + exit 1."""
    import loregist.config as config_mod
    from loregist import project_cmd

    monkeypatch.setattr(
        config_mod,
        "infer_project",
        lambda cwd=None, explicit=None: (_ for _ in ()).throw(
            ValueError("프로젝트를 추론할 수 없습니다")
        ),
    )
    monkeypatch.delenv("LOREGIST_CWD", raising=False)

    rc = project_cmd.main(["current"])
    captured = capsys.readouterr()

    assert rc == 1, f"infer_project ValueError 시 exit 1이어야 함, 실제: {rc}"
    assert "프로젝트를 추론할 수 없습니다" in captured.err, (
        f"오류 메시지가 stderr에 있어야 함, 실제: {captured.err!r}"
    )


# ══════════════════════════════════════════════════════════════
# 알 수 없는 서브커맨드 → exit 2
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_unknown_subcommand_exits_2(monkeypatch, capsys):
    """Error: 알 수 없는 서브커맨드 → exit 2."""
    from loregist import project_cmd

    rc = project_cmd.main(["nonexistent-subcmd"])
    assert rc == 2, f"알 수 없는 서브커맨드는 exit 2여야 함, 실제: {rc}"


@pytest.mark.unit
def test_no_subcommand_exits_2(monkeypatch, capsys):
    """Error: 서브커맨드 없이 호출 → exit 2 (usage 출력)."""
    from loregist import project_cmd

    rc = project_cmd.main([])
    assert rc == 2, f"서브커맨드 없이 호출 시 exit 2여야 함, 실제: {rc}"


@pytest.mark.unit
def test_unknown_subcommand_stderr_message(monkeypatch, capsys):
    """Error: 알 수 없는 서브커맨드 → stderr에 오류 메시지 포함."""
    from loregist import project_cmd

    project_cmd.main(["badcmd"])
    captured = capsys.readouterr()
    assert "badcmd" in captured.err, (
        f"알 수 없는 서브커맨드명이 stderr에 포함되어야 함, 실제: {captured.err!r}"
    )


# ══════════════════════════════════════════════════════════════
# G-4: dump_projects JSON 출력 키 검증 — 'handbook' 있고 'wiki'/'wiki_sources' 없음
# ══════════════════════════════════════════════════════════════


def _make_fake_projects_with_handbook():
    """dump_projects 출력 키 검증용 PROJECTS 딕셔너리 (내부 필드 'handbook' 사용)."""
    return {
        "handbook-proj": {
            "docs_root": Path("/fake/workspace/handbook-proj/dev"),
            "vault": Path("/fake/workspace/logvault/handbook-proj"),
            "cold": None,
            "done": None,
            "catalog": Path("/fake/workspace/handbook-proj/dev/_wiki"),
            "vault_cleanup": {"active": False, "retention_days": None},
            "handbook": [
                {"path": Path("/fake/workspace/tools/test/handbook/page.md"), "writable": False, "update_when": None},
                {"path": Path("/fake/workspace/tools/test/handbook/policy.md"), "writable": True, "update_when": "daily"},
            ],
            "catalog_readme": None,
            "extensions": ["md"],
            "hot_days": 30,
        },
        "no-handbook-proj": {
            "docs_root": Path("/fake/workspace/no-handbook-proj/dev"),
            "vault": Path("/fake/workspace/logvault/no-handbook-proj"),
            "cold": None,
            "done": None,
            "catalog": None,
            "vault_cleanup": {"active": False, "retention_days": None},
            "handbook": [],
            "catalog_readme": None,
            "extensions": ["md"],
            "hot_days": 30,
        },
    }


@pytest.mark.unit
def test_dump_projects_output_key_is_handbook_not_wiki(monkeypatch, capsys):
    """
    G-4: dump_projects() 출력 JSON의 최상위 키에 'handbook'이 있고
    'wiki'/'wiki_sources'는 없음을 검증.
    """
    import loregist.config as config_mod

    fake_projects = _make_fake_projects_with_handbook()
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    import json
    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "handbook-proj")
    assert "handbook" in proj, (
        f"dump_projects 출력에 'handbook' 키가 있어야 함, 실제 키: {list(proj.keys())}"
    )
    assert "wiki" not in proj, (
        f"dump_projects 출력에 'wiki' 키가 없어야 함"
    )
    assert "wiki_sources" not in proj, (
        f"dump_projects 출력에 'wiki_sources' 키가 없어야 함"
    )


@pytest.mark.unit
def test_dump_projects_handbook_items_structure(monkeypatch, capsys):
    """
    G-4: dump_projects() 출력 JSON의 'handbook' 각 원소가
    path/writable/update_when 3키를 가진다.
    """
    import loregist.config as config_mod

    fake_projects = _make_fake_projects_with_handbook()
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    import json
    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "handbook-proj")
    hb = proj["handbook"]
    assert len(hb) == 2
    for item in hb:
        assert set(item.keys()) >= {"path", "writable", "update_when"}, (
            f"'handbook' 원소가 path/writable/update_when 3키를 가져야 함, 실제: {item}"
        )


@pytest.mark.unit
def test_dump_projects_handbook_empty_when_no_handbook(monkeypatch, capsys):
    """
    G-4: handbook 미선언 프로젝트의 dump_projects 출력에서 'handbook'이 빈 리스트.
    """
    import loregist.config as config_mod

    fake_projects = _make_fake_projects_with_handbook()
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    import json
    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "no-handbook-proj")
    assert proj["handbook"] == [], (
        f"handbook 미선언 프로젝트의 'handbook' 값이 빈 리스트여야 함, 실제: {proj['handbook']}"
    )
    assert "wiki_sources" not in proj
    assert "wiki" not in proj


# ══════════════════════════════════════════════════════════════
# D3: dump_projects exists 플래그 단위 테스트
# ══════════════════════════════════════════════════════════════


def _make_projects_with_exists_handbook(tmp_path: Path):
    """exists 플래그 검증용 PROJECTS 딕셔너리.

    - handbook-exists-proj: handbook 파일 1개 실제 존재(tmp_path), 1개 부재(가짜 경로)
    - no-handbook-proj: handbook 항목 없음
    """
    real_handbook = tmp_path / "real_handbook.md"
    real_handbook.write_text("# Real Handbook\n", encoding="utf-8")

    fake_handbook = Path("/nonexistent/path/fake_handbook.md")
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    return {
        "handbook-exists-proj": {
            "docs_root": tmp_path,
            "vault": None,
            "cold": None,
            "done": None,
            "catalog": catalog_dir,
            "vault_cleanup": {"active": False, "retention_days": None},
            "handbook": [
                {"path": real_handbook, "writable": True, "update_when": None},
                {"path": fake_handbook, "writable": False, "update_when": None},
            ],
            "catalog_readme": None,
            "extensions": ["md"],
            "hot_days": 30,
        },
        "no-handbook-proj": {
            "docs_root": tmp_path,
            "vault": None,
            "cold": None,
            "done": None,
            "catalog": None,
            "vault_cleanup": {"active": False, "retention_days": None},
            "handbook": [],
            "catalog_readme": None,
            "extensions": ["md"],
            "hot_days": 30,
        },
    }


@pytest.mark.unit
def test_dump_projects_handbook_exists_true_for_real_file(tmp_path, monkeypatch):
    """D3: 실제 존재하는 handbook 파일에는 exists=true가 설정된다."""
    import loregist.config as config_mod
    import json

    fake_projects = _make_projects_with_exists_handbook(tmp_path)
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "handbook-exists-proj")
    real_item = next(w for w in proj["handbook"] if "real_handbook.md" in w["path"])
    assert real_item["exists"] is True, (
        f"실제 존재하는 handbook 파일에 exists=True가 있어야 함, 실제: {real_item}"
    )


@pytest.mark.unit
def test_dump_projects_handbook_exists_false_for_missing_file(tmp_path, monkeypatch):
    """D3: 존재하지 않는 handbook 파일에는 exists=false가 설정된다."""
    import loregist.config as config_mod
    import json

    fake_projects = _make_projects_with_exists_handbook(tmp_path)
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "handbook-exists-proj")
    fake_item = next(w for w in proj["handbook"] if "fake_handbook.md" in w["path"])
    assert fake_item["exists"] is False, (
        f"존재하지 않는 handbook 파일에 exists=False가 있어야 함, 실제: {fake_item}"
    )


@pytest.mark.unit
def test_dump_projects_handbook_empty_array_has_no_exists_items(tmp_path, monkeypatch):
    """D3: handbook 항목이 0개인 프로젝트에서 'handbook' 배열이 빈 리스트이고 exists 관련 오류 없음."""
    import loregist.config as config_mod
    import json

    fake_projects = _make_projects_with_exists_handbook(tmp_path)
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "no-handbook-proj")
    assert proj["handbook"] == [], (
        f"handbook 미선언 프로젝트의 'handbook' 값이 빈 리스트여야 함, 실제: {proj['handbook']}"
    )
    # handbook_exists_count는 0
    assert proj.get("handbook_exists_count", 0) == 0, (
        f"handbook 미선언 프로젝트의 handbook_exists_count가 0이어야 함, 실제: {proj.get('handbook_exists_count')}"
    )


@pytest.mark.unit
def test_dump_projects_handbook_exists_count(tmp_path, monkeypatch):
    """D3: handbook_exists_count가 exists=True 항목 수와 일치한다."""
    import loregist.config as config_mod
    import json

    fake_projects = _make_projects_with_exists_handbook(tmp_path)
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "handbook-exists-proj")
    exists_true_count = sum(1 for w in proj["handbook"] if w["exists"] is True)
    assert proj["handbook_exists_count"] == exists_true_count, (
        f"handbook_exists_count({proj['handbook_exists_count']})가 "
        f"exists=True 항목 수({exists_true_count})와 일치해야 함"
    )


@pytest.mark.unit
def test_dump_projects_catalog_exists_true_when_dir_present(tmp_path, monkeypatch):
    """D3: catalog 디렉토리가 실제 존재하면 catalog_exists=True."""
    import loregist.config as config_mod
    import json

    fake_projects = _make_projects_with_exists_handbook(tmp_path)
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "handbook-exists-proj")
    assert proj["catalog_exists"] is True, (
        f"catalog 디렉토리가 존재하면 catalog_exists=True여야 함, 실제: {proj.get('catalog_exists')}"
    )


@pytest.mark.unit
def test_dump_projects_catalog_exists_false_when_no_catalog(tmp_path, monkeypatch):
    """D3: catalog 미설정 프로젝트에는 catalog_exists=False."""
    import loregist.config as config_mod
    import json

    fake_projects = _make_projects_with_exists_handbook(tmp_path)
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "no-handbook-proj")
    assert proj["catalog_exists"] is False, (
        f"catalog 미설정 프로젝트의 catalog_exists=False여야 함, 실제: {proj.get('catalog_exists')}"
    )


@pytest.mark.unit
def test_dump_projects_handbook_item_preserves_existing_fields(tmp_path, monkeypatch):
    """D3 Conformance: exists 추가 후에도 path/writable/update_when 기존 필드가 보존된다."""
    import loregist.config as config_mod
    import json

    fake_projects = _make_projects_with_exists_handbook(tmp_path)
    monkeypatch.setattr(config_mod, "PROJECTS", fake_projects)

    raw = config_mod.dump_projects(as_json=True)
    data = json.loads(raw)

    proj = next(p for p in data if p["name"] == "handbook-exists-proj")
    for item in proj["handbook"]:
        assert "path" in item, f"path 필드가 보존되어야 함, 실제: {item}"
        assert "writable" in item, f"writable 필드가 보존되어야 함, 실제: {item}"
        assert "update_when" in item, f"update_when 필드가 보존되어야 함, 실제: {item}"
        assert "exists" in item, f"exists 필드가 추가되어야 함, 실제: {item}"

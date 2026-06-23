"""
tests/test_onboard.py
G-1: onboard.py 단위 테스트 — 기본값 추론·검증·블록 생성 (DB 불요)

모든 테스트는 @pytest.mark.unit.
실제 projects.toml 오염 없음 — tmp_path + monkeypatch로 PROJECTS_FILE / WORKSPACE 격리.
외부 subprocess(embed/catalog) 호출 없음 — 함수 단위 직접 검증.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────
# 헬퍼: 임시 projects.toml 생성
# ──────────────────────────────────────────────────────────────

_MINIMAL_TOML_HEADER = """\
# loregist projects.toml (test)
[projects]
"""

_EXISTING_BLOCK = """\
[projects.existing-proj]
docs_root = "tools/existing/dev"
vault     = "logvault/existing"
cold      = "logvault/existing/cold"
"""


def _make_toml(tmp_path: Path, content: str = "") -> Path:
    """임시 projects.toml 생성 후 경로 반환."""
    p = tmp_path / "projects.toml"
    p.write_text(content, encoding="utf-8")
    return p


# ══════════════════════════════════════════════════════════════
# B-2: 기본값 추론
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalize_key_lowercase(monkeypatch, tmp_path):
    """B-2 / Boundary: 대문자 폴더명 → 소문자 키."""
    from loregist.onboard_input import _normalize_key
    assert _normalize_key("MyProject") == "myproject"


@pytest.mark.unit
def test_normalize_key_spaces_to_hyphens(monkeypatch, tmp_path):
    """B-2 / Boundary: 공백 포함('My Proj') → 'my-proj'."""
    from loregist.onboard_input import _normalize_key
    assert _normalize_key("My Proj") == "my-proj"


@pytest.mark.unit
def test_normalize_key_special_chars_stripped():
    """B-2: 하이픈·소문자·숫자 이외 문자 제거."""
    from loregist.onboard_input import _normalize_key
    assert _normalize_key("My@Proj!2024") == "myproj2024"


@pytest.mark.unit
def test_normalize_key_leading_hyphen_stripped():
    """B-2 / Range: 선두 하이픈 제거 후 유효 키 반환."""
    from loregist.onboard_input import _normalize_key
    # "_proj" → "-proj" (underscore 제거) → 선두 하이픈 제거 → "proj"
    result = _normalize_key("_proj")
    assert not result.startswith("-"), f"선두 하이픈이 없어야 함, 실제: {result!r}"


@pytest.mark.unit
def test_normalize_key_empty_fallback():
    """B-2 / Existence: 빈 문자열 → 'project' 폴백."""
    from loregist.onboard_input import _normalize_key
    assert _normalize_key("") == "project"


@pytest.mark.unit
def test_default_key_uses_cwd_name(tmp_path):
    """B-2: _default_key → cwd 폴더명 정규화 결과."""
    from loregist.onboard_input import _default_key
    # tmp_path의 마지막 세그먼트가 폴더명
    key = _default_key(tmp_path)
    # 정규화 결과는 소문자·숫자·하이픈만
    import re
    assert re.match(r"^[a-z0-9][a-z0-9-]*$", key), (
        f"_default_key 결과가 ^[a-z0-9][a-z0-9-]*$ 를 만족해야 함, 실제: {key!r}"
    )


@pytest.mark.unit
def test_default_docs_root_relative_to_workspace(tmp_path, monkeypatch):
    """B-2: cwd가 WORKSPACE 아래이면 상대경로+/dev 형태로 반환."""
    import loregist.config as config_mod
    from loregist.onboard_input import _default_docs_root

    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()
    cwd = fake_workspace / "myrepo"
    cwd.mkdir()

    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)
    # onboard_input은 함수 내부에서 `from loregist.config import WORKSPACE` 로 매번 import하므로
    # config_mod.WORKSPACE 패치만으로 충분

    result = _default_docs_root(cwd, "myrepo")
    # 결과가 "myrepo/dev" 또는 절대경로가 아닌 상대경로 형태여야 함
    assert result.endswith("/dev"), f"docs_root 기본값이 /dev로 끝나야 함, 실제: {result!r}"
    assert "myrepo" in result, f"docs_root 기본값에 'myrepo'가 포함되어야 함, 실제: {result!r}"


@pytest.mark.unit
def test_default_docs_root_fallback_outside_workspace(tmp_path, monkeypatch):
    """B-2: cwd가 WORKSPACE 밖이면 fallback 경로 반환."""
    import loregist.config as config_mod
    from loregist.onboard_input import _default_docs_root

    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()
    outside_cwd = tmp_path / "outside_dir"
    outside_cwd.mkdir()

    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)

    result = _default_docs_root(outside_cwd, "outside-proj")
    assert "outside-proj" in result, (
        f"WORKSPACE 밖 cwd의 fallback docs_root에 키가 포함되어야 함, 실제: {result!r}"
    )
    assert result.endswith("/dev"), (
        f"fallback docs_root가 /dev로 끝나야 함, 실제: {result!r}"
    )


@pytest.mark.unit
def test_default_vault_and_cold():
    """B-2: vault/cold 기본값 패턴 확인."""
    from loregist.onboard_input import _default_vault, _default_cold
    assert _default_vault("mykey") == "logvault/mykey"
    assert _default_cold("mykey") == "logvault/mykey/cold"


# ══════════════════════════════════════════════════════════════
# B-3: 키 정규식 검증 (_validate_key)
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_validate_key_valid():
    """B-3 / Right: 유효 키는 None 반환."""
    from loregist.onboard_input import _validate_key
    assert _validate_key("myproj") is None
    assert _validate_key("my-proj2") is None
    assert _validate_key("a") is None
    assert _validate_key("proj-123") is None


@pytest.mark.unit
def test_validate_key_empty_rejected():
    """B-3 / Range: 빈 키 → 오류 메시지 반환."""
    from loregist.onboard_input import _validate_key
    result = _validate_key("")
    assert result is not None, "빈 키는 오류를 반환해야 함"


@pytest.mark.unit
def test_validate_key_leading_hyphen_rejected():
    """B-3 / Range: 선두 하이픈('--proj') → 오류 메시지 반환."""
    from loregist.onboard_input import _validate_key
    result = _validate_key("-proj")
    assert result is not None, "선두 하이픈 키는 오류를 반환해야 함"


@pytest.mark.unit
def test_validate_key_uppercase_rejected():
    """B-3 / Range: 대문자 포함 키 → 오류 메시지 반환."""
    from loregist.onboard_input import _validate_key
    result = _validate_key("MyProj")
    assert result is not None, "대문자 포함 키는 오류를 반환해야 함"


@pytest.mark.unit
def test_validate_key_space_rejected():
    """B-3 / Range: 공백 포함 키 → 오류 메시지 반환."""
    from loregist.onboard_input import _validate_key
    result = _validate_key("my proj")
    assert result is not None, "공백 포함 키는 오류를 반환해야 함"


@pytest.mark.unit
def test_validate_key_underscore_rejected():
    """B-3 / Range: 언더스코어 포함 키 → 오류 메시지 반환."""
    from loregist.onboard_input import _validate_key
    result = _validate_key("my_proj")
    assert result is not None, "언더스코어 포함 키는 오류를 반환해야 함"


# ══════════════════════════════════════════════════════════════
# B-3: 중복 키 거부 (_check_duplicate, load_projects)
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_check_duplicate_existing_key(tmp_path, monkeypatch):
    """B-3 / Error: 이미 등록된 키 → _check_duplicate는 True 반환."""
    import loregist.config as config_mod
    from loregist.onboard_input import _check_duplicate

    toml_content = """\
[projects.already-exists]
docs_root = "tools/test/dev"
vault     = "logvault/test"
cold      = "logvault/test/cold"
"""
    toml_path = _make_toml(tmp_path, toml_content)
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)
    # load_projects도 새 파일 참조하도록 PROJECTS_FILE 패치만으로 충분 (_check_duplicate 내부 동적 import)

    assert _check_duplicate("already-exists") is True


@pytest.mark.unit
def test_check_duplicate_new_key(tmp_path, monkeypatch):
    """B-3: 새 키 → _check_duplicate는 False 반환."""
    import loregist.config as config_mod
    from loregist.onboard_input import _check_duplicate

    toml_content = """\
[projects.existing]
docs_root = "tools/existing/dev"
vault     = "logvault/existing"
cold      = "logvault/existing/cold"
"""
    toml_path = _make_toml(tmp_path, toml_content)
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)

    assert _check_duplicate("brand-new-key") is False


@pytest.mark.unit
def test_check_duplicate_missing_file(tmp_path, monkeypatch):
    """B-3 / Existence: projects.toml 없으면 _check_duplicate는 False (FileNotFoundError 처리)."""
    import loregist.config as config_mod
    from loregist.onboard_input import _check_duplicate

    nonexistent = tmp_path / "no_file.toml"
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", nonexistent)

    assert _check_duplicate("any-key") is False


# ══════════════════════════════════════════════════════════════
# B-3: 경로 traversal 거부 (_validate_path)
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_validate_path_dotdot_rejected(tmp_path, monkeypatch):
    """B-3 / Error: '..' 포함 경로 → 오류 메시지 반환."""
    import loregist.config as config_mod
    from loregist.onboard_input import _validate_path

    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)

    _, err = _validate_path("../escape/path", "test")
    assert err is not None, "'..' 포함 경로는 오류를 반환해야 함"


@pytest.mark.unit
def test_validate_path_valid_relative(tmp_path, monkeypatch):
    """B-3 / Right: 유효 상대경로 → 오류 없음."""
    import loregist.config as config_mod
    from loregist.onboard_input import _validate_path

    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)

    _, err = _validate_path("tools/myproj/dev", "test")
    assert err is None, f"유효 상대경로는 오류가 없어야 함, 실제: {err!r}"


@pytest.mark.unit
def test_validate_path_absolute_outside_workspace_rejected(tmp_path, monkeypatch):
    """B-3 / Error: WORKSPACE 밖 절대경로 → 오류 메시지 반환."""
    import loregist.config as config_mod
    from loregist.onboard_input import _validate_path

    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)

    outside_abs = str(tmp_path / "outside" / "path")
    _, err = _validate_path(outside_abs, "test")
    assert err is not None, "WORKSPACE 밖 절대경로는 오류를 반환해야 함"


# ══════════════════════════════════════════════════════════════
# C-1: TOML 블록 생성 + 역방향(Inverse) 재파싱
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_build_toml_block_docs_root_parseable():
    """C-1 / Inverse: docs_root형 블록 생성 → tomllib.loads로 키·경로 무손실 파싱."""
    from loregist.onboard import _build_toml_block

    block = _build_toml_block(
        key="tc-block",
        proj_type="docs_root",
        docs_root="tools/tc-block/dev",
        vault="logvault/tc-block",
        cold_or_done="logvault/tc-block/cold",
        catalog=False,
    )

    # 최소 TOML 헤더 없이 섹션 블록 단독으로 파싱
    data = tomllib.loads(block)
    proj = data["projects"]["tc-block"]
    assert proj["docs_root"] == "tools/tc-block/dev", (
        f"docs_root 손실, 실제: {proj.get('docs_root')!r}"
    )
    assert proj["vault"] == "logvault/tc-block", (
        f"vault 손실, 실제: {proj.get('vault')!r}"
    )
    assert proj["cold"] == "logvault/tc-block/cold", (
        f"cold 손실, 실제: {proj.get('cold')!r}"
    )
    assert "catalog" not in proj, "catalog opt-out이면 catalog 키가 없어야 함"


@pytest.mark.unit
def test_build_toml_block_docs_root_with_catalog_parseable():
    """C-1 / Conformance: docs_root형 + catalog=True 블록 → tomllib 파싱 + catalog=true 포함."""
    from loregist.onboard import _build_toml_block

    block = _build_toml_block(
        key="tc-catalog",
        proj_type="docs_root",
        docs_root="tools/tc-catalog/dev",
        vault="logvault/tc-catalog",
        cold_or_done="logvault/tc-catalog/cold",
        catalog=True,
    )

    data = tomllib.loads(block)
    proj = data["projects"]["tc-catalog"]
    assert proj.get("catalog") is True, (
        f"catalog opt-in 시 catalog=true여야 함, 실제: {proj.get('catalog')!r}"
    )


@pytest.mark.unit
def test_build_toml_block_done_parseable():
    """C-1 / Inverse: done형 블록 생성 → tomllib.loads로 키·경로 무손실 파싱."""
    from loregist.onboard import _build_toml_block

    block = _build_toml_block(
        key="tc-done",
        proj_type="done",
        docs_root=None,
        vault="logvault/tc-done",
        cold_or_done="tc-done/plans/done",
        catalog=False,
    )

    data = tomllib.loads(block)
    proj = data["projects"]["tc-done"]
    assert proj["vault"] == "logvault/tc-done", f"vault 손실, 실제: {proj.get('vault')!r}"
    assert proj["done"] == "tc-done/plans/done", f"done 손실, 실제: {proj.get('done')!r}"
    assert "docs_root" not in proj, "done형에 docs_root가 없어야 함"
    assert "cold" not in proj, "done형에 cold가 없어야 함"


@pytest.mark.unit
def test_build_toml_block_done_with_catalog_parseable():
    """C-1 / Conformance: done형 + catalog=True → tomllib 파싱 + catalog=true."""
    from loregist.onboard import _build_toml_block

    block = _build_toml_block(
        key="tc-done-cat",
        proj_type="done",
        docs_root=None,
        vault="logvault/tc-done-cat",
        cold_or_done="tc-done-cat/plans/done",
        catalog=True,
    )

    data = tomllib.loads(block)
    proj = data["projects"]["tc-done-cat"]
    assert proj.get("catalog") is True, (
        f"done형 catalog opt-in 시 catalog=true여야 함, 실제: {proj.get('catalog')!r}"
    )


@pytest.mark.unit
def test_append_toml_preserves_existing_header(tmp_path, monkeypatch):
    """C-1 / Inverse + Ordering: 기존 헤더·블록 보존, append 후 tomllib 재파싱 성공."""
    import loregist.config as config_mod
    from loregist.onboard import _build_toml_block, _append_toml

    existing_content = """\
# loregist projects.toml — 테스트 헤더

[projects.existing]
docs_root = "tools/existing/dev"
vault     = "logvault/existing"
cold      = "logvault/existing/cold"
"""
    toml_path = _make_toml(tmp_path, existing_content)
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)

    block = _build_toml_block(
        key="appended",
        proj_type="docs_root",
        docs_root="tools/appended/dev",
        vault="logvault/appended",
        cold_or_done="logvault/appended/cold",
        catalog=False,
    )
    _append_toml("appended", block)

    content_after = toml_path.read_text(encoding="utf-8")
    # 기존 헤더 주석 보존
    assert "# loregist projects.toml" in content_after, "헤더 주석이 보존되어야 함"
    # 기존 블록 보존
    assert "[projects.existing]" in content_after, "기존 프로젝트 블록이 보존되어야 함"
    # 새 블록 추가
    assert "[projects.appended]" in content_after, "새 블록이 추가되어야 함"

    # tomllib 재파싱 성공
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    assert "existing" in data["projects"], "기존 프로젝트가 파싱되어야 함"
    assert "appended" in data["projects"], "추가된 프로젝트가 파싱되어야 함"


@pytest.mark.unit
def test_append_toml_rejects_duplicate(tmp_path, monkeypatch):
    """C-1 / Error: 이미 등록된 키 재append 시도 → ValueError."""
    import loregist.config as config_mod
    from loregist.onboard import _build_toml_block, _append_toml

    existing_content = """\
[projects.dup-key]
docs_root = "tools/dup/dev"
vault     = "logvault/dup"
cold      = "logvault/dup/cold"
"""
    toml_path = _make_toml(tmp_path, existing_content)
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)

    block = _build_toml_block(
        key="dup-key",
        proj_type="docs_root",
        docs_root="tools/dup/dev",
        vault="logvault/dup",
        cold_or_done="logvault/dup/cold",
        catalog=False,
    )
    with pytest.raises(ValueError, match="dup-key"):
        _append_toml("dup-key", block)


# ══════════════════════════════════════════════════════════════
# B-4: 비-TTY 가드
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_non_tty_without_project_exits_nonzero(tmp_path, monkeypatch):
    """B-4 / Time + Error: 비-TTY에서 --project 누락 시 exit≠0, input() 호출 없음."""
    import loregist.config as config_mod

    # stdin이 TTY가 아닌 것처럼 패치
    monkeypatch.setattr("sys.stdin", open(os.devnull))

    # projects.toml 격리
    toml_path = _make_toml(tmp_path, "[projects]\n")
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)
    monkeypatch.setattr(config_mod, "WORKSPACE", tmp_path)

    from loregist.onboard import main

    rc = main([])  # --project 없이 비-TTY
    assert rc != 0, f"비-TTY에서 --project 누락 시 exit≠0이어야 함, 실제: {rc}"


import os


@pytest.mark.unit
def test_non_tty_with_project_does_not_call_input(tmp_path, monkeypatch):
    """B-4 / Time: 비-TTY에서 --project 지정 시 input() 호출 없이 진행 (subprocess만 막음)."""
    import loregist.config as config_mod
    from loregist.onboard import main

    # stdin 비-TTY 패치
    monkeypatch.setattr("sys.stdin", open(os.devnull))

    # projects.toml 격리 (비어 있음 — 기존 키 없음)
    toml_path = _make_toml(tmp_path, "")
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)

    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)

    # _run_embed, _run_catalog_init subprocess 차단
    import loregist.onboard as onboard_mod
    monkeypatch.setattr(onboard_mod, "_run_embed", lambda key: 0)
    monkeypatch.setattr(onboard_mod, "_run_catalog_init", lambda key: 0)

    # input() 호출 감지
    called = []

    def fake_input(prompt=""):
        called.append(prompt)
        return ""

    monkeypatch.setattr("builtins.input", fake_input)

    docs_root_dir = tmp_path / "workspace" / "tcproj" / "dev"
    docs_root_dir.mkdir(parents=True)

    rc = main([
        "--project", "tcproj",
        "--type", "docs_root",
        "--docs-root", "tcproj/dev",
        "--vault", "logvault/tcproj",
        "--cold", "logvault/tcproj/cold",
        "--yes",
    ])
    assert not called, f"비-TTY + 모든 플래그 지정 시 input() 호출이 없어야 함, 실제 호출: {called}"
    # 성공(0) 또는 embed 실패(2) 모두 허용, 단 1(인자 오류)은 아님
    assert rc in (0, 2), f"성공 또는 embed 실패(2) 코드여야 함, 실제: {rc}"


# ══════════════════════════════════════════════════════════════
# Cardinality: 0개 toml에서 add → 1개
# ══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_append_toml_to_empty_file(tmp_path, monkeypatch):
    """Cardinality: 빈 projects.toml에 블록 append → 1개 프로젝트 파싱."""
    import loregist.config as config_mod
    from loregist.onboard import _build_toml_block, _append_toml

    toml_path = _make_toml(tmp_path, "")
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)

    block = _build_toml_block(
        key="first-proj",
        proj_type="docs_root",
        docs_root="tools/first/dev",
        vault="logvault/first",
        cold_or_done="logvault/first/cold",
        catalog=False,
    )
    _append_toml("first-proj", block)

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    assert len(data.get("projects", {})) == 1, (
        f"빈 toml → append 후 1개 프로젝트여야 함, 실제: {len(data.get('projects', {}))}"
    )

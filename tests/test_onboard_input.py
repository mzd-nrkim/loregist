"""
tests/test_onboard_input.py
입력 수집 계층(onboard_input.py) 전용 단위 테스트.

모든 테스트는 @pytest.mark.unit.
DB 불요 — 함수 단위 직접 검증.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _make_toml(tmp_path: Path, content: str = "") -> Path:
    p = tmp_path / "projects.toml"
    p.write_text(content, encoding="utf-8")
    return p


# ══════════════════════════════════════════════════════════════
# _ask_key: flag_project 지정 시 바로 반환
# ══════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_ask_key_with_flag_project_returns_flag(tmp_path, monkeypatch):
    """_ask_key(flag_project='my-proj', is_tty=False, cwd=...) → 'my-proj' 반환."""
    import loregist.config as config_mod
    from loregist.onboard_input import _ask_key

    # projects.toml 격리 — 중복 없음
    toml_path = _make_toml(tmp_path, "")
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)

    result = _ask_key(flag_project="my-proj", is_tty=False, cwd=tmp_path)
    assert result == "my-proj", f"flag_project 지정 시 그대로 반환해야 함, 실제: {result!r}"


# ══════════════════════════════════════════════════════════════
# _ask_key: flag_project=None, is_tty=False → default key 반환
# ══════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_ask_key_no_flag_non_tty_returns_default(tmp_path, monkeypatch):
    """_ask_key(flag_project=None, is_tty=False, cwd=<tmp_path>) → cwd 폴더명 기반 default key."""
    import loregist.config as config_mod
    from loregist.onboard_input import _ask_key, _normalize_key

    # projects.toml 격리 — 중복 없음
    toml_path = _make_toml(tmp_path, "")
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)

    # is_tty=False이면 input() 없이 기본값(cwd.name 정규화)을 반환해야 함
    expected_default = _normalize_key(tmp_path.name)
    result = _ask_key(flag_project=None, is_tty=False, cwd=tmp_path)
    assert result == expected_default, (
        f"비-TTY에서 flag_project=None이면 default key를 반환해야 함, "
        f"기대: {expected_default!r}, 실제: {result!r}"
    )


# ══════════════════════════════════════════════════════════════
# _ask_key: 유효하지 않은 flag_project → sys.exit(1)
# ══════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_ask_key_invalid_flag_exits(tmp_path, monkeypatch):
    """_ask_key에 유효하지 않은 키를 flag로 전달 → SystemExit."""
    import loregist.config as config_mod
    from loregist.onboard_input import _ask_key

    toml_path = _make_toml(tmp_path, "")
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)

    with pytest.raises(SystemExit):
        _ask_key(flag_project="-invalid-key", is_tty=False, cwd=tmp_path)


# ══════════════════════════════════════════════════════════════
# _validate_path: '..' 포함 경로 → 오류
# ══════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_validate_path_dotdot_rejected(tmp_path, monkeypatch):
    """_validate_path: '..' 포함 경로 → 오류 메시지 반환."""
    import loregist.config as config_mod
    from loregist.onboard_input import _validate_path

    fake_ws = tmp_path / "workspace"
    fake_ws.mkdir()
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_ws)

    _, err = _validate_path("../escape", "label")
    assert err is not None, "'..' 포함 경로는 오류를 반환해야 함"


@pytest.mark.unit
def test_validate_path_valid_relative_ok(tmp_path, monkeypatch):
    """_validate_path: 유효 상대경로 → 오류 없음."""
    import loregist.config as config_mod
    from loregist.onboard_input import _validate_path

    fake_ws = tmp_path / "workspace"
    fake_ws.mkdir()
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_ws)

    _, err = _validate_path("tools/myproj/dev", "label")
    assert err is None, f"유효 상대경로는 오류가 없어야 함, 실제: {err!r}"

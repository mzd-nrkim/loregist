"""단위 테스트: loregist watch — 확장자 필터 + 범위 검증 (embed_file mock)"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _make_projects(tmp_path: Path) -> dict:
    vault = tmp_path / "vault" / "testproj"
    vault.mkdir(parents=True, exist_ok=True)
    return {
        "testproj": {
            "vault": vault,
            "docs_root": None,
            "done": None,
            "cold": None,
        }
    }


# ──────────────────────────────────────────────────────────────
# B-6-1: 확장자 필터 (_is_target)
# ──────────────────────────────────────────────────────────────

def test_is_target_log_and_md():
    """기본 extensions로 초기화된 핸들러는 .log, .md를 대상으로 인식하고 그 외는 무시한다."""
    from loregist.watch import _EmbedHandler

    fake_projects = {
        "testproj": {
            "vault": None,
            "docs_root": None,
            "done": None,
            "cold": None,
            "extensions": ["log", "md"],
        }
    }
    with patch("loregist.watch.PROJECTS", fake_projects):
        handler = _EmbedHandler(project="testproj")
        assert handler._is_target("notes/2026-01-01.log") is True
        assert handler._is_target("docs/readme.md") is True
        assert handler._is_target("image.png") is False
        assert handler._is_target("data.csv") is False
        assert handler._is_target("script.py") is False
        assert handler._is_target("noext") is False


# ──────────────────────────────────────────────────────────────
# B-6-2: _EmbedHandler — *.log 변경 → embed_file 호출 (Reference)
# ──────────────────────────────────────────────────────────────

def test_handler_calls_embed_file_on_log(tmp_path):
    """on_modified 에서 *.log 파일 → embed_file 이 정확히 1회 호출된다."""
    from loregist.watch import _EmbedHandler

    mock_conn = MagicMock()
    mock_embed = MagicMock()
    fake_event = MagicMock()
    fake_event.is_directory = False
    fake_event.src_path = str(tmp_path / "test.log")

    with patch("loregist.watch.get_db_connection") as mock_ctx, \
         patch("loregist.watch.embed_file", mock_embed), \
         patch("loregist.watch.PROJECTS", {"testproj": {"vault": None, "docs_root": None, "done": None, "cold": None, "extensions": ["log", "md"]}}):
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        handler = _EmbedHandler(project="testproj")
        handler.on_modified(fake_event)

    mock_embed.assert_called_once_with(mock_conn, "testproj", fake_event.src_path)


def test_handler_calls_embed_file_on_md(tmp_path):
    """on_created 에서 *.md 파일 → embed_file 이 정확히 1회 호출된다."""
    from loregist.watch import _EmbedHandler

    mock_conn = MagicMock()
    mock_embed = MagicMock()
    fake_event = MagicMock()
    fake_event.is_directory = False
    fake_event.src_path = str(tmp_path / "readme.md")

    with patch("loregist.watch.get_db_connection") as mock_ctx, \
         patch("loregist.watch.embed_file", mock_embed), \
         patch("loregist.watch.PROJECTS", {"testproj": {"vault": None, "docs_root": None, "done": None, "cold": None, "extensions": ["log", "md"]}}):
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        handler = _EmbedHandler(project="testproj")
        handler.on_created(fake_event)

    mock_embed.assert_called_once_with(mock_conn, "testproj", fake_event.src_path)


# ──────────────────────────────────────────────────────────────
# B-6-3: _EmbedHandler — 비대상 확장자 → embed_file 미호출
# ──────────────────────────────────────────────────────────────

def test_handler_ignores_non_target_extension(tmp_path):
    """*.png 등 비대상 확장자 변경 시 embed_file 을 호출하지 않는다."""
    from loregist.watch import _EmbedHandler

    mock_embed = MagicMock()
    fake_event = MagicMock()
    fake_event.is_directory = False
    fake_event.src_path = str(tmp_path / "image.png")

    with patch("loregist.watch.embed_file", mock_embed), \
         patch("loregist.watch.PROJECTS", {"testproj": {"vault": None, "docs_root": None, "done": None, "cold": None, "extensions": ["log", "md"]}}):
        handler = _EmbedHandler(project="testproj")
        handler.on_modified(fake_event)

    mock_embed.assert_not_called()


# ──────────────────────────────────────────────────────────────
# B-6-4: 디렉터리 이벤트 무시
# ──────────────────────────────────────────────────────────────

def test_handler_ignores_directory_events(tmp_path):
    """is_directory=True 이벤트는 무시한다."""
    from loregist.watch import _EmbedHandler

    mock_embed = MagicMock()
    fake_event = MagicMock()
    fake_event.is_directory = True
    fake_event.src_path = str(tmp_path / "somedir.log")

    with patch("loregist.watch.embed_file", mock_embed), \
         patch("loregist.watch.PROJECTS", {"testproj": {"vault": None, "docs_root": None, "done": None, "cold": None, "extensions": ["log", "md"]}}):
        handler = _EmbedHandler(project="testproj")
        handler.on_modified(fake_event)

    mock_embed.assert_not_called()


# ──────────────────────────────────────────────────────────────
# B-6-5: _validate_dir_in_project — 범위 안 → 통과 (Reference)
# ──────────────────────────────────────────────────────────────

def test_validate_dir_inside_project_passes(tmp_path):
    """vault 하위 디렉터리는 --project 없이도 통과한다."""
    from loregist.watch import _validate_dir_in_project

    projects = _make_projects(tmp_path)
    sub_dir = tmp_path / "vault" / "testproj" / "journal"
    sub_dir.mkdir(parents=True, exist_ok=True)

    with patch("loregist.watch.PROJECTS", projects):
        # 예외 없이 반환되어야 한다
        _validate_dir_in_project(sub_dir, "testproj", explicit_project=None)


# ──────────────────────────────────────────────────────────────
# B-6-6: _validate_dir_in_project — 범위 밖 + --project 없음 → exit (Error)
# ──────────────────────────────────────────────────────────────

def test_validate_dir_outside_project_exits(tmp_path):
    """project 범위 밖 디렉터리 + --project 미지정 → sys.exit(1)."""
    from loregist.watch import _validate_dir_in_project

    projects = _make_projects(tmp_path)
    outside_dir = Path("/tmp/unrelated-directory-xyz")

    with patch("loregist.watch.PROJECTS", projects), \
         pytest.raises(SystemExit) as exc_info:
        _validate_dir_in_project(outside_dir, "testproj", explicit_project=None)

    assert exc_info.value.code == 1


# ──────────────────────────────────────────────────────────────
# B-6-7: _validate_dir_in_project — 범위 밖이어도 --project 명시 → 통과
# ──────────────────────────────────────────────────────────────

def test_validate_dir_outside_but_explicit_project_passes(tmp_path):
    """--project 를 명시하면 범위 밖 디렉터리도 허용된다."""
    from loregist.watch import _validate_dir_in_project

    projects = _make_projects(tmp_path)
    outside_dir = Path("/tmp/unrelated-directory-xyz")

    with patch("loregist.watch.PROJECTS", projects):
        # explicit_project 지정 시 범위 검사 스킵 → 예외 없이 반환
        _validate_dir_in_project(outside_dir, "testproj", explicit_project="testproj")


# ──────────────────────────────────────────────────────────────
# B-6-8: extensions 커스텀 값 — ["txt"]만 설정 시 .txt 대상, .md/.log 비대상
# ──────────────────────────────────────────────────────────────

def test_handler_custom_extensions():
    """extensions = ["txt"] 설정 시 .txt만 대상, .md/.log는 무시한다."""
    from loregist.watch import _EmbedHandler

    fake_projects = {
        "testproj": {
            "vault": None,
            "docs_root": None,
            "done": None,
            "cold": None,
            "extensions": ["txt"],
        }
    }
    with patch("loregist.watch.PROJECTS", fake_projects):
        handler = _EmbedHandler(project="testproj")
        assert handler._is_target("note.txt") is True
        assert handler._is_target("readme.md") is False
        assert handler._is_target("app.log") is False
        assert handler._is_target("data.csv") is False

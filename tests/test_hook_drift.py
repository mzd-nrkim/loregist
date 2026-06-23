"""단위 테스트: hooks/post_embed_drift.py의 decide_reminder 순수 함수.

@pytest.mark.unit — 서브프로세스 없이 함수를 직접 import해 검증한다.
monkeypatch만 사용하며 importlib.reload / 전역 재대입 금지.

pytest.ini의 pythonpath = src tests hooks 설정으로 hooks 디렉토리가
자동으로 sys.path에 포함되므로 별도 경로 조작 불필요.
"""
import pytest


# ─────────────────────────────────────────────────────────────
# 테스트 대상 임포트 (loregist config는 실제 PROJECTS 로드 시도)
# projects.toml 이 없으면 SystemExit; conftest에서 LOREGIST_PROJECTS_FILE을 처리한다.
# 여기서는 decide_reminder 만 테스트하므로 loregist.config.decide_entry_skill의
# 실제 동작을 연동한다.
# ─────────────────────────────────────────────────────────────
import post_embed_drift as _hook_mod

decide_reminder = _hook_mod.decide_reminder


# ─────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────

EMBED_CMD = "loregist embed --project myproj /some/path"
EMBED_CMD_NO_PROJECT = "loregist embed /some/path"


# ─────────────────────────────────────────────────────────────
# 테스트 케이스
# ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDecideReminder:
    """decide_reminder 순수 함수 단위 테스트."""

    # ------------------------------------------------------------------
    # 기본 매칭 + 플래그 off/off → 제안형 리마인더
    # ------------------------------------------------------------------

    def test_embed_in_session_with_drift_both_off_returns_suggestion(self):
        """embed 매칭 + in_session=True + drift>0 + (off,off) → 제안 리마인더 반환."""
        result = decide_reminder(
            tool_name="Bash",
            command=EMBED_CMD,
            in_session=True,
            drift_count=3,
            handbook_on=False,
            catalog_on=False,
        )
        assert result is not None
        assert "3" in result
        assert "wiki-update" in result or "수행할까요" in result
        # 플래그 정보 포함 확인
        assert "auto_handbook_update=off" in result
        assert "auto_catalog_update=off" in result

    # ------------------------------------------------------------------
    # D-5: 읽기전용 커맨드는 None 반환
    # ------------------------------------------------------------------

    def test_loregist_search_returns_none(self):
        """loregist search 커맨드 → None (D-5 읽기전용 제외)."""
        result = decide_reminder(
            tool_name="Bash",
            command="loregist search --project myproj keyword",
            in_session=True,
            drift_count=5,
            handbook_on=True,
            catalog_on=True,
        )
        assert result is None

    def test_loregist_status_returns_none(self):
        """loregist status 커맨드 → None (D-5)."""
        result = decide_reminder(
            tool_name="Bash",
            command="loregist status",
            in_session=True,
            drift_count=2,
            handbook_on=True,
            catalog_on=False,
        )
        assert result is None

    def test_loregist_project_list_returns_none(self):
        """loregist project list 커맨드 → None (D-5)."""
        result = decide_reminder(
            tool_name="Bash",
            command="loregist project list",
            in_session=True,
            drift_count=1,
            handbook_on=False,
            catalog_on=True,
        )
        assert result is None

    # ------------------------------------------------------------------
    # drift_count=0 → None (노이즈 차단)
    # ------------------------------------------------------------------

    def test_zero_drift_returns_none(self):
        """drift_count=0 → None (노이즈 없음)."""
        result = decide_reminder(
            tool_name="Bash",
            command=EMBED_CMD,
            in_session=True,
            drift_count=0,
            handbook_on=True,
            catalog_on=True,
        )
        assert result is None

    # ------------------------------------------------------------------
    # in_session=False → None (세션 밖 제외, B-4)
    # ------------------------------------------------------------------

    def test_not_in_session_returns_none(self):
        """in_session=False → None (세션 밖 제외, B-4 경로 분리)."""
        result = decide_reminder(
            tool_name="Bash",
            command=EMBED_CMD,
            in_session=False,
            drift_count=4,
            handbook_on=True,
            catalog_on=True,
        )
        assert result is None

    # ------------------------------------------------------------------
    # tool_name != Bash → None
    # ------------------------------------------------------------------

    def test_non_bash_tool_returns_none(self):
        """tool_name이 Bash가 아니면 → None."""
        result = decide_reminder(
            tool_name="Edit",
            command=EMBED_CMD,
            in_session=True,
            drift_count=2,
            handbook_on=True,
            catalog_on=True,
        )
        assert result is None

    # ------------------------------------------------------------------
    # 플래그 조합 4가지 — 진입 스킬 반영 확인
    # ------------------------------------------------------------------

    def test_both_on_returns_wiki_update(self):
        """handbook_on=True, catalog_on=True → wiki-update 리마인더."""
        result = decide_reminder(
            tool_name="Bash",
            command=EMBED_CMD,
            in_session=True,
            drift_count=2,
            handbook_on=True,
            catalog_on=True,
        )
        assert result is not None
        assert "wiki-update" in result
        assert "auto_handbook_update=on" in result
        assert "auto_catalog_update=on" in result

    def test_handbook_on_catalog_off_returns_handbook_update(self):
        """handbook_on=True, catalog_on=False → handbook-update 리마인더."""
        result = decide_reminder(
            tool_name="Bash",
            command=EMBED_CMD,
            in_session=True,
            drift_count=1,
            handbook_on=True,
            catalog_on=False,
        )
        assert result is not None
        assert "handbook-update" in result
        assert "auto_handbook_update=on" in result
        assert "auto_catalog_update=off" in result

    def test_handbook_off_catalog_on_returns_catalog_update(self):
        """handbook_on=False, catalog_on=True → catalog-update 리마인더."""
        result = decide_reminder(
            tool_name="Bash",
            command=EMBED_CMD,
            in_session=True,
            drift_count=7,
            handbook_on=False,
            catalog_on=True,
        )
        assert result is not None
        assert "catalog-update" in result
        assert "auto_handbook_update=off" in result
        assert "auto_catalog_update=on" in result

    def test_both_off_returns_suggestion(self):
        """handbook_on=False, catalog_on=False → 제안형 리마인더(진입 스킬 없음)."""
        result = decide_reminder(
            tool_name="Bash",
            command=EMBED_CMD,
            in_session=True,
            drift_count=5,
            handbook_on=False,
            catalog_on=False,
        )
        assert result is not None
        assert "수행할까요" in result
        assert "wiki-update" in result
        assert "auto_handbook_update=off" in result
        assert "auto_catalog_update=off" in result

    # ------------------------------------------------------------------
    # drift_count 가 리마인더에 반영되는지 확인
    # ------------------------------------------------------------------

    def test_drift_count_appears_in_reminder(self):
        """drift_count 숫자가 리마인더 문자열에 포함된다."""
        result = decide_reminder(
            tool_name="Bash",
            command=EMBED_CMD,
            in_session=True,
            drift_count=42,
            handbook_on=False,
            catalog_on=False,
        )
        assert result is not None
        assert "42" in result

    # ------------------------------------------------------------------
    # 내용변경성 embed 패턴 엣지케이스
    # ------------------------------------------------------------------

    def test_embed_subcommand_with_flags_matches(self):
        """loregist embed --project foo /path → 내용변경성, 매칭됨."""
        result = decide_reminder(
            tool_name="Bash",
            command="loregist embed --project foo /some/path",
            in_session=True,
            drift_count=1,
            handbook_on=False,
            catalog_on=False,
        )
        assert result is not None

    def test_loregist_without_embed_returns_none(self):
        """loregist 명령이지만 embed 서브커맨드가 없으면 → None."""
        result = decide_reminder(
            tool_name="Bash",
            command="loregist watch --project foo",
            in_session=True,
            drift_count=3,
            handbook_on=True,
            catalog_on=True,
        )
        assert result is None

    def test_non_loregist_command_returns_none(self):
        """loregist 관련 없는 커맨드 → None."""
        result = decide_reminder(
            tool_name="Bash",
            command="git status",
            in_session=True,
            drift_count=3,
            handbook_on=True,
            catalog_on=True,
        )
        assert result is None


# ─────────────────────────────────────────────────────────────
# _is_content_changing_embed 헬퍼 직접 테스트
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestIsContentChangingEmbed:
    """_is_content_changing_embed 내부 헬퍼 단위 테스트."""

    def test_embed_matches(self):
        assert _hook_mod._is_content_changing_embed("loregist embed /path") is True

    def test_embed_with_flags_matches(self):
        assert _hook_mod._is_content_changing_embed(
            "loregist embed --project foo /bar"
        ) is True

    def test_search_does_not_match(self):
        assert _hook_mod._is_content_changing_embed("loregist search foo") is False

    def test_status_does_not_match(self):
        assert _hook_mod._is_content_changing_embed("loregist status") is False

    def test_project_list_does_not_match(self):
        assert _hook_mod._is_content_changing_embed("loregist project list") is False

    def test_embed_preceded_by_whitespace_matches(self):
        """loregist embed 앞에 공백이 있어도 매칭 (예: 파이프라인 앞 공백)."""
        assert _hook_mod._is_content_changing_embed("  loregist embed /path") is True

    def test_empty_command_does_not_match(self):
        assert _hook_mod._is_content_changing_embed("") is False

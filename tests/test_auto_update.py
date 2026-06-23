"""
tests/test_auto_update.py — auto_update 모듈 단위 테스트 (Phase C+D1+D-c)

Verification 9: 자동 기동 억제(B-4·C-3), allowedTools 분기,
재귀 가드 주입, 인증 실패 graceful(C-4), 리포트 파싱(D-1).
D-c: _resolve_claude_bin PATH 해석 우선순위 검증.

모든 테스트는 @pytest.mark.unit 마킹.
subprocess는 monkeypatch로 mock — 실제 claude를 기동하지 않는다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import types

import pytest

from loregist import auto_update


# ──────────────────────────────────────────────────────────────
# _resolve_claude_bin — PATH 해석 우선순위 (D-c)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestResolveClaudeBin:
    """_resolve_claude_bin() 해석 우선순위 단위 테스트.

    전역 상태를 변경하지 않도록 monkeypatch만 사용한다.
    """

    def test_loregist_claude_bin_env_takes_priority(self, monkeypatch):
        """(1) LOREGIST_CLAUDE_BIN 설정 시 그 값을 반환한다."""
        monkeypatch.setenv("LOREGIST_CLAUDE_BIN", "/custom/bin/claude")
        # which나 glob이 어떤 값을 반환하든 env 값이 우선이어야 한다
        monkeypatch.setattr(auto_update.shutil, "which", lambda name: "/should/not/use")
        result = auto_update._resolve_claude_bin()
        assert result == "/custom/bin/claude"

    def test_shutil_which_used_when_no_env(self, monkeypatch):
        """(2) LOREGIST_CLAUDE_BIN 미설정 + shutil.which가 경로 반환 → 그 경로를 사용한다."""
        monkeypatch.delenv("LOREGIST_CLAUDE_BIN", raising=False)
        monkeypatch.setattr(auto_update.shutil, "which", lambda name: "/usr/bin/claude")
        result = auto_update._resolve_claude_bin()
        assert result == "/usr/bin/claude"

    def test_nvm_glob_used_when_which_returns_none(self, monkeypatch, tmp_path):
        """(3) env 미설정 + which=None + nvm glob 경로 존재 → glob 최신 경로 반환."""
        monkeypatch.delenv("LOREGIST_CLAUDE_BIN", raising=False)
        monkeypatch.setattr(auto_update.shutil, "which", lambda name: None)

        # 실제 파일을 tmp_path에 만들어 os.path.isfile을 mock 없이 통과
        node_v18 = tmp_path / "v18.0.0" / "bin"
        node_v20 = tmp_path / "v20.9.0" / "bin"
        node_v18.mkdir(parents=True)
        node_v20.mkdir(parents=True)
        claude_v18 = node_v18 / "claude"
        claude_v20 = node_v20 / "claude"
        claude_v18.touch()
        claude_v20.touch()

        fake_nvm_paths = [str(claude_v18), str(claude_v20)]

        # glob.glob만 mock — isfile은 실제 파일로 통과
        monkeypatch.setattr(auto_update.glob, "glob", lambda pattern: fake_nvm_paths)

        result = auto_update._resolve_claude_bin()
        # sorted()[-1] → 알파벳 기준 마지막(v20.9.0이 v18.0.0보다 뒤)
        assert result == str(claude_v20)

    def test_fallback_to_claude_string_when_nothing_found(self, monkeypatch):
        """(5) 모두 실패 → 문자열 "claude" 반환(기존 동작 폴백)."""
        monkeypatch.delenv("LOREGIST_CLAUDE_BIN", raising=False)
        monkeypatch.setattr(auto_update.shutil, "which", lambda name: None)
        # glob이 빈 리스트 → nvm 경로 없음; Homebrew 경로도 실제 없으면 폴백
        monkeypatch.setattr(auto_update.glob, "glob", lambda pattern: [])
        # /opt/homebrew/bin/claude, /usr/local/bin/claude 를 isfile이 False 반환하도록
        # auto_update 모듈의 os.path.isfile을 교체 (함수 참조 수준)
        monkeypatch.setattr(auto_update.os.path, "isfile", lambda p: False)

        result = auto_update._resolve_claude_bin()
        assert result == "claude"

    def test_build_claude_command_uses_resolved_bin(self, monkeypatch):
        """build_claude_command() argv[0]이 _resolve_claude_bin() 결과를 쓰는지 확인."""
        monkeypatch.setenv("LOREGIST_CLAUDE_BIN", "/nvm/bin/claude")
        cmd = auto_update.build_claude_command("catalog-update", "proj")
        assert cmd[0] == "/nvm/bin/claude"


# ──────────────────────────────────────────────────────────────
# should_auto_launch — 자동 기동 억제 (B-4·C-3, Verification 9)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestShouldAutoLaunch:
    """should_auto_launch 순수 판정 함수 단위 테스트."""

    def test_suppressed_by_claudecode(self):
        """(a) CLAUDECODE 존재 → None (세션 안 — hook 처리, B-4)."""
        result = auto_update.should_auto_launch(
            {"CLAUDECODE": "1"},
            handbook_on=True,
            catalog_on=True,
            drift_count=5,
        )
        assert result is None

    def test_suppressed_by_auto_guard(self):
        """(b) LOREGIST_AUTO_GUARD 존재 → None (재귀 가드, C-3)."""
        result = auto_update.should_auto_launch(
            {"LOREGIST_AUTO_GUARD": "1"},
            handbook_on=True,
            catalog_on=True,
            drift_count=5,
        )
        assert result is None

    def test_suppressed_no_drift(self):
        """(c) 가드 없음 + drift=0 → None."""
        result = auto_update.should_auto_launch(
            {},
            handbook_on=True,
            catalog_on=True,
            drift_count=0,
        )
        assert result is None

    def test_suppressed_both_flags_off(self):
        """(d) 가드 없음 + drift>0 + 두 플래그 모두 off → None."""
        result = auto_update.should_auto_launch(
            {},
            handbook_on=False,
            catalog_on=False,
            drift_count=3,
        )
        assert result is None

    def test_returns_entry_skill_catalog_only(self):
        """(e-1) 가드 없음 + drift>0 + catalog_on=True → "catalog-update"."""
        result = auto_update.should_auto_launch(
            {},
            handbook_on=False,
            catalog_on=True,
            drift_count=2,
        )
        assert result == "catalog-update"

    def test_returns_entry_skill_handbook_only(self):
        """(e-2) 가드 없음 + drift>0 + handbook_on=True → "handbook-update"."""
        result = auto_update.should_auto_launch(
            {},
            handbook_on=True,
            catalog_on=False,
            drift_count=1,
        )
        assert result == "handbook-update"

    def test_returns_entry_skill_both_on(self):
        """(e-3) 가드 없음 + drift>0 + 두 플래그 모두 on → "wiki-update"."""
        result = auto_update.should_auto_launch(
            {},
            handbook_on=True,
            catalog_on=True,
            drift_count=1,
        )
        assert result == "wiki-update"

    def test_suppressed_by_claudecode_overrides_guard(self):
        """CLAUDECODE + LOREGIST_AUTO_GUARD 둘 다 있어도 억제(CLAUDECODE 먼저 체크)."""
        result = auto_update.should_auto_launch(
            {"CLAUDECODE": "1", "LOREGIST_AUTO_GUARD": "1"},
            handbook_on=True,
            catalog_on=True,
            drift_count=5,
        )
        assert result is None


# ──────────────────────────────────────────────────────────────
# build_claude_command — allowedTools 분기
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBuildClaudeCommand:
    """build_claude_command allowedTools 분기 테스트."""

    def test_wiki_update_includes_agent(self):
        """wiki-update → Agent 포함."""
        cmd = auto_update.build_claude_command("wiki-update", "myproject")
        tools_idx = cmd.index("--allowedTools") + 1
        tools = cmd[tools_idx]
        assert "Agent" in tools.split(",")

    def test_catalog_update_excludes_agent(self):
        """catalog-update → Agent 미포함."""
        cmd = auto_update.build_claude_command("catalog-update", "myproject")
        tools_idx = cmd.index("--allowedTools") + 1
        tools = cmd[tools_idx]
        assert "Agent" not in tools.split(",")

    def test_handbook_update_excludes_agent(self):
        """handbook-update → Agent 미포함."""
        cmd = auto_update.build_claude_command("handbook-update", "myproject")
        tools_idx = cmd.index("--allowedTools") + 1
        tools = cmd[tools_idx]
        assert "Agent" not in tools.split(",")

    def test_command_structure(self):
        """argv 구조: claude -p <prompt> --permission-mode acceptEdits --output-format json."""
        cmd = auto_update.build_claude_command("catalog-update", "testproj")
        # claude는 절대경로로 해석될 수 있음(_resolve_claude_bin) — 경로 무관 basename으로 검증
        assert cmd[0] == "claude" or cmd[0].endswith("/claude")
        assert "-p" in cmd
        assert "--permission-mode" in cmd
        assert "acceptEdits" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_prompt_contains_skill_and_project(self):
        """프롬프트에 스킬명과 프로젝트명 포함."""
        cmd = auto_update.build_claude_command("handbook-update", "loregist")
        p_idx = cmd.index("-p") + 1
        prompt = cmd[p_idx]
        assert "/handbook-update" in prompt
        assert "loregist" in prompt


# ──────────────────────────────────────────────────────────────
# launch_headless — 재귀 가드 주입 + 인증 실패 graceful (C-3, C-4)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestLaunchHeadless:
    """launch_headless 단위 테스트 — subprocess.run mock."""

    def _make_proc(self, returncode=0, stdout="", stderr=""):
        """subprocess.CompletedProcess 유사 객체 생성."""
        proc = types.SimpleNamespace(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
        return proc

    def test_auto_guard_injected_in_child_env(self, monkeypatch):
        """재귀 가드: 자식 env에 LOREGIST_AUTO_GUARD=1 주입 확인 (C-3)."""
        captured_env = {}

        def mock_run(argv, *, env, cwd, capture_output, text):
            captured_env.update(env)
            return self._make_proc(returncode=0, stdout=json.dumps({"summary": "ok"}))

        monkeypatch.setattr(subprocess, "run", mock_run)
        auto_update.launch_headless("catalog-update", "proj", "/tmp")
        assert captured_env.get("LOREGIST_AUTO_GUARD") == "1"

    def test_nonzero_return_code_ok_false(self, monkeypatch):
        """returncode != 0 → ok=False + drift_surfaced=True (C-4)."""
        def mock_run(argv, *, env, cwd, capture_output, text):
            return self._make_proc(returncode=1, stderr="authentication error")

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = auto_update.launch_headless("catalog-update", "proj", "/tmp")
        assert result["ok"] is False
        assert result.get("drift_surfaced") is True
        assert "error" in result

    def test_nonzero_return_code_no_exception(self, monkeypatch):
        """returncode != 0 → 예외 발생 없음 (graceful, C-4)."""
        def mock_run(argv, *, env, cwd, capture_output, text):
            return self._make_proc(returncode=127, stderr="command not found")

        monkeypatch.setattr(subprocess, "run", mock_run)
        # 예외 미발생 검증
        result = auto_update.launch_headless("handbook-update", "proj", "/tmp")
        assert isinstance(result, dict)
        assert result["ok"] is False

    def test_file_not_found_graceful(self, monkeypatch):
        """claude 실행 파일 없음(FileNotFoundError) → ok=False + drift_surfaced=True."""
        def mock_run(argv, *, env, cwd, capture_output, text):
            raise FileNotFoundError("No such file: claude")

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = auto_update.launch_headless("wiki-update", "proj", "/tmp")
        assert result["ok"] is False
        assert result.get("drift_surfaced") is True

    def test_success_returns_parsed_report(self, monkeypatch):
        """returncode=0 → parse_report 결과 반환."""
        payload = json.dumps({"summary": "2 files updated", "changed_files": ["a.md", "b.md"]})

        def mock_run(argv, *, env, cwd, capture_output, text):
            return self._make_proc(returncode=0, stdout=payload)

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = auto_update.launch_headless("catalog-update", "proj", "/tmp")
        assert result["ok"] is True
        assert result["summary"] == "2 files updated"
        assert result["changed_files"] == ["a.md", "b.md"]

    def test_cwd_passed_to_subprocess(self, monkeypatch):
        """지정한 cwd가 subprocess.run에 전달되는지 확인."""
        captured = {}

        def mock_run(argv, *, env, cwd, capture_output, text):
            captured["cwd"] = cwd
            return self._make_proc(returncode=0, stdout="{}")

        monkeypatch.setattr(subprocess, "run", mock_run)
        auto_update.launch_headless("catalog-update", "proj", "/home/user/project")
        assert captured["cwd"] == "/home/user/project"


# ──────────────────────────────────────────────────────────────
# parse_report — 리포트 파싱 (D-1)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestParseReport:
    """parse_report 단위 테스트."""

    def test_valid_json_with_summary_and_files(self):
        """표준 스키마 파싱."""
        payload = json.dumps({
            "summary": "handbook 3개 갱신됨",
            "changed_files": ["docs/ARCHITECTURE.md", "docs/README.md"],
        })
        result = auto_update.parse_report(payload)
        assert result["ok"] is True
        assert result["summary"] == "handbook 3개 갱신됨"
        assert "docs/ARCHITECTURE.md" in result["changed_files"]

    def test_invalid_json_safe_fallback(self):
        """깨진 JSON → 안전 fallback (ok=True, changed_files=[], summary=raw[:500])."""
        raw = "not json at all }"
        result = auto_update.parse_report(raw)
        assert result["ok"] is True
        assert result["changed_files"] == []
        assert result["summary"] == raw[:500]

    def test_empty_string_fallback(self):
        """빈 문자열 → 안전 fallback."""
        result = auto_update.parse_report("")
        assert result["ok"] is True
        assert result["changed_files"] == []

    def test_json_without_changed_files(self):
        """changed_files 키 없음 → 빈 리스트."""
        payload = json.dumps({"summary": "done"})
        result = auto_update.parse_report(payload)
        assert result["ok"] is True
        assert result["changed_files"] == []
        assert result["summary"] == "done"

    def test_json_without_summary(self):
        """summary 키 없음 → summary 빈 문자열."""
        payload = json.dumps({"changed_files": ["x.md"]})
        result = auto_update.parse_report(payload)
        assert result["ok"] is True
        assert result["summary"] == ""
        assert result["changed_files"] == ["x.md"]

    def test_result_key_used_as_summary_fallback(self):
        """summary 없고 result 키 있음 → result를 summary로."""
        payload = json.dumps({"result": "catalog updated"})
        result = auto_update.parse_report(payload)
        assert result["summary"] == "catalog updated"

    def test_content_list_format(self):
        """content 배열 형식(Claude API 스타일) 파싱."""
        payload = json.dumps({
            "content": [
                {"type": "text", "text": "갱신 완료"},
            ]
        })
        result = auto_update.parse_report(payload)
        assert result["summary"] == "갱신 완료"

    def test_non_dict_json_fallback(self):
        """JSON이지만 dict가 아닌 값(배열 등) → 안전 fallback."""
        payload = json.dumps(["a", "b"])
        result = auto_update.parse_report(payload)
        assert result["ok"] is True
        assert result["changed_files"] == []

    def test_files_key_alternative(self):
        """changed_files 없고 files 키 있음 → files를 changed_files로."""
        payload = json.dumps({"files": ["a.md", "b.md"], "summary": "ok"})
        result = auto_update.parse_report(payload)
        assert result["changed_files"] == ["a.md", "b.md"]


# ──────────────────────────────────────────────────────────────
# report_log — 출력 테스트 (D-1)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestReportLog:
    """report_log 출력 단위 테스트."""

    def test_success_result_printed(self, capsys):
        """성공 결과가 stdout에 출력된다."""
        result = {
            "ok": True,
            "changed_files": ["foo.md"],
            "summary": "1 file changed",
        }
        auto_update.report_log(result)
        captured = capsys.readouterr()
        assert "헤드리스 갱신 완료" in captured.out
        assert "foo.md" in captured.out
        assert "1 file changed" in captured.out

    def test_failure_result_printed(self, capsys):
        """실패 결과가 drift 신호와 함께 출력된다."""
        result = {
            "ok": False,
            "error": "claude not found",
            "drift_surfaced": True,
        }
        auto_update.report_log(result)
        captured = capsys.readouterr()
        assert "실패" in captured.out
        assert "수동 갱신" in captured.out

    def test_log_target_file(self, tmp_path):
        """log_target 지정 시 파일에 기록된다."""
        log_file = tmp_path / "auto_update.log"
        result = {"ok": True, "changed_files": [], "summary": "done"}
        auto_update.report_log(result, log_target=str(log_file))
        content = log_file.read_text(encoding="utf-8")
        assert "헤드리스 갱신 완료" in content


# ──────────────────────────────────────────────────────────────
# embed.main 헤드리스 분기 cwd 정합 (Phase B)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestEmbedHeadlessCwd:
    """embed.main()의 헤드리스 분기가 LOREGIST_CWD 환경변수를
    launch_headless의 cwd 인자로 올바르게 전달하는지 검증한다.

    embed.main() 전체를 monkeypatch로 격리하여 단위 호출한다.
    """

    def _patch_embed_main(self, monkeypatch, env_updates: dict):
        """embed.main() 호출에 필요한 모든 의존성을 mock하고
        launch_headless 호출 인자를 캡처해 반환하는 dict를 준비한다."""
        import argparse
        import contextlib
        from loregist import embed as _embed

        # os.environ 환경 변수 교체 (테스트 범위 내)
        for k, v in env_updates.items():
            monkeypatch.setenv(k, v)

        # argparse: --project 없이 parse_args()가 기본값 Namespace 반환
        fake_args = argparse.Namespace(
            project=None,
            dry_run=False,
            incremental=False,
            include_today=False,
        )
        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: fake_args)

        # infer_project → embed.py가 from loregist.config import infer_project로 가져옴
        monkeypatch.setattr(_embed, "infer_project", lambda explicit=None: "testproj")

        # PROJECTS — embed 모듈이 참조하는 심볼
        fake_projects = {
            "testproj": {
                "auto_handbook_update": True,
                "auto_catalog_update": True,
            }
        }
        monkeypatch.setattr(_embed, "PROJECTS", fake_projects)

        # discover_embed_files → 빈 리스트 (파일 처리 루프 스킵)
        monkeypatch.setattr(_embed, "discover_embed_files", lambda project, include_today=False: [])

        # get_db_connection → no-op contextmanager
        @contextlib.contextmanager
        def fake_db():
            yield None

        monkeypatch.setattr(_embed, "get_db_connection", fake_db)

        # write_embed_log → no-op
        monkeypatch.setattr(_embed, "write_embed_log", lambda **kw: None)

        # _drift.compute_drift → drift 있음 (헤드리스 분기 진입 조건)
        monkeypatch.setattr(_embed._drift, "compute_drift", lambda project: ["fake.md"])

        # should_auto_launch → "catalog-update" 반환 (헤드리스 분기 진입)
        monkeypatch.setattr(_embed.auto_update, "should_auto_launch",
                            lambda env, handbook_on, catalog_on, drift_count: "catalog-update")

        # launch_headless 캡처
        captured = {}

        def fake_launch(entry, project, cwd):
            captured["cwd"] = cwd
            captured["entry"] = entry
            captured["project"] = project
            return {"ok": True, "changed_files": [], "summary": "ok"}

        monkeypatch.setattr(_embed.auto_update, "launch_headless", fake_launch)

        # report_log → no-op
        monkeypatch.setattr(_embed.auto_update, "report_log", lambda result, **kw: None)

        return captured

    def test_headless_cwd_uses_loregist_cwd_env(self, monkeypatch):
        """LOREGIST_CWD 설정 시 launch_headless에 해당 경로가 전달된다."""
        from loregist import embed as _embed

        captured = self._patch_embed_main(monkeypatch, {"LOREGIST_CWD": "/some/path"})
        _embed.main()
        assert captured.get("cwd") == "/some/path"

    def test_headless_cwd_fallback_to_getcwd(self, monkeypatch):
        """LOREGIST_CWD 미설정 시 os.getcwd() 값이 launch_headless에 전달된다."""
        import os
        from loregist import embed as _embed

        monkeypatch.delenv("LOREGIST_CWD", raising=False)
        expected_cwd = os.getcwd()
        captured = self._patch_embed_main(monkeypatch, {})
        _embed.main()
        assert captured.get("cwd") == expected_cwd


# ──────────────────────────────────────────────────────────────
# git_tracked_changes — git 상태 파싱 (D-1)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGitTrackedChanges:
    """git_tracked_changes 단위 테스트."""

    def _make_proc(self, returncode=0, stdout=""):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    def test_parses_porcelain_output(self, monkeypatch):
        """git status --porcelain 출력을 파싱해 경로 목록 반환."""
        def mock_run(argv, *, cwd, capture_output, text):
            return self._make_proc(stdout=" M docs/README.md\nA  src/new.py\n")

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = auto_update.git_tracked_changes("/tmp/proj")
        assert "docs/README.md" in result
        assert "src/new.py" in result

    def test_empty_output(self, monkeypatch):
        """변경 없으면 빈 리스트."""
        def mock_run(argv, *, cwd, capture_output, text):
            return self._make_proc(stdout="")

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = auto_update.git_tracked_changes("/tmp/proj")
        assert result == []

    def test_git_not_found(self, monkeypatch):
        """git 실행 불가 → 빈 리스트(예외 미발생)."""
        def mock_run(argv, *, cwd, capture_output, text):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = auto_update.git_tracked_changes("/tmp/proj")
        assert result == []

    def test_nonzero_exit(self, monkeypatch):
        """git returncode != 0 → 빈 리스트."""
        def mock_run(argv, *, cwd, capture_output, text):
            return self._make_proc(returncode=128)

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = auto_update.git_tracked_changes("/tmp/proj")
        assert result == []

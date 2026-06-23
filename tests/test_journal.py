"""단위 테스트: loregist journal (tmp_path mock)"""
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ──────────────────────────────────────────────────────────────
# 헬퍼: PROJECTS / infer_project 를 tmp_path 기반으로 mock
# ──────────────────────────────────────────────────────────────

def _make_projects(tmp_path: Path) -> dict:
    vault = tmp_path / "vault" / "testproj"
    return {"testproj": {"vault": vault, "docs_root": None}}


def _run_journal(args: list[str], tmp_path: Path, extra_projects: dict | None = None):
    """journal.main() 을 sys.argv 패치 + PROJECTS mock 으로 실행한다."""
    projects = extra_projects if extra_projects is not None else _make_projects(tmp_path)
    with patch("loregist.journal.PROJECTS", projects), \
         patch("loregist.journal.infer_project", return_value="testproj"), \
         patch.object(sys, "argv", ["loregist-journal"] + args):
        from loregist import journal
        journal.main()


# ──────────────────────────────────────────────────────────────
# A-4-1: 경로 및 포맷 검증 (Right)
# ──────────────────────────────────────────────────────────────

def test_journal_appends_correct_format(tmp_path):
    """[HH:MM] 메시지 포맷으로 vault/journal/<today>.log 에 기록된다."""
    import datetime
    from loregist import journal

    projects = _make_projects(tmp_path)

    with patch("loregist.journal.PROJECTS", projects), \
         patch("loregist.journal.infer_project", return_value="testproj"):
        journal.run_journal("테스트 메모", project=None)

    today = datetime.date.today().strftime("%Y-%m-%d")
    log_path = tmp_path / "vault" / "testproj" / "journal" / f"{today}.log"

    assert log_path.exists(), "로그 파일이 생성되어야 한다"
    content = log_path.read_text(encoding="utf-8")
    pattern = r"^\[\d{2}:\d{2}\] 테스트 메모\n$"
    assert re.match(pattern, content), f"포맷 불일치: {content!r}"


# ──────────────────────────────────────────────────────────────
# A-4-2: append — 덮어쓰기 금지 (Ordering / CORRECT)
# ──────────────────────────────────────────────────────────────

def test_journal_appends_multiple_lines(tmp_path):
    """두 번 호출 시 파일에 두 줄이 순서대로 누적된다 (덮어쓰기 금지)."""
    import datetime
    from loregist import journal

    projects = _make_projects(tmp_path)

    with patch("loregist.journal.PROJECTS", projects), \
         patch("loregist.journal.infer_project", return_value="testproj"):
        journal.run_journal("첫째", project=None)
        journal.run_journal("둘째", project=None)

    today = datetime.date.today().strftime("%Y-%m-%d")
    log_path = tmp_path / "vault" / "testproj" / "journal" / f"{today}.log"
    lines = log_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2, f"2줄이어야 한다: {lines}"
    assert "첫째" in lines[0]
    assert "둘째" in lines[1]


# ──────────────────────────────────────────────────────────────
# A-4-3: 디렉터리/파일 자동 생성 (Existence / CORRECT)
# ──────────────────────────────────────────────────────────────

def test_journal_creates_dir_and_file(tmp_path):
    """vault/journal 디렉터리가 없어도 자동으로 생성된다."""
    import datetime
    from loregist import journal

    projects = _make_projects(tmp_path)
    journal_dir = tmp_path / "vault" / "testproj" / "journal"
    assert not journal_dir.exists(), "사전 조건: 디렉터리 없어야 한다"

    with patch("loregist.journal.PROJECTS", projects), \
         patch("loregist.journal.infer_project", return_value="testproj"):
        journal.run_journal("자동 생성 테스트", project=None)

    today = datetime.date.today().strftime("%Y-%m-%d")
    assert (journal_dir / f"{today}.log").exists()


# ──────────────────────────────────────────────────────────────
# A-4-4: 인수 없이 실행 → usage + exit 2 (Boundary)
# ──────────────────────────────────────────────────────────────

def test_journal_no_args_exits_2(tmp_path):
    """메시지 없이 실행하면 exit(2)로 종료하고 파일을 생성하지 않는다."""
    import datetime
    from loregist import journal

    projects = _make_projects(tmp_path)

    with patch("loregist.journal.PROJECTS", projects), \
         patch("loregist.journal.infer_project", return_value="testproj"), \
         patch.object(sys, "argv", ["loregist-journal"]), \
         pytest.raises(SystemExit) as exc_info:
        journal.main()

    assert exc_info.value.code == 2

    today = datetime.date.today().strftime("%Y-%m-%d")
    log_path = tmp_path / "vault" / "testproj" / "journal" / f"{today}.log"
    assert not log_path.exists(), "메시지 없이는 파일이 생성되면 안 된다"


# ──────────────────────────────────────────────────────────────
# A-4-5: 타임스탬프 포맷 (Conformance / CORRECT)
# ──────────────────────────────────────────────────────────────

def test_journal_timestamp_format(tmp_path):
    """기록된 라인이 정확히 [HH:MM] 포맷을 따른다."""
    import datetime
    from loregist import journal

    projects = _make_projects(tmp_path)

    with patch("loregist.journal.PROJECTS", projects), \
         patch("loregist.journal.infer_project", return_value="testproj"):
        journal.run_journal("포맷 확인", project=None)

    today = datetime.date.today().strftime("%Y-%m-%d")
    log_path = tmp_path / "vault" / "testproj" / "journal" / f"{today}.log"
    line = log_path.read_text(encoding="utf-8").strip()
    assert re.match(r"^\[\d{2}:\d{2}\] .+$", line), f"타임스탬프 포맷 불일치: {line!r}"

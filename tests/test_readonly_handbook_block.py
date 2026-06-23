"""
tests/test_readonly_handbook_block.py
P5-E: writable=false handbook 코드 레벨 차단 자동 테스트

TC 커버 목록:
  1. 차단       — writable=false handbook 경로가 get_readonly_handbook_paths에 포함 & hook이 Edit 차단(exit 2)
  2. 문자열도 차단 — 문자열 형식 항목(writable 미지정=false)도 집합에 포함·차단
  3. 통과        — writable=true handbook 경로는 집합에 없고 hook이 통과(exit 0)
  4. 과차단 없음  — 집합 밖 임의 파일 Edit 통과 / Edit·Write·NotebookEdit 외 tool 통과
  5. Boundary   — 빈 handbook 목록·writable 키 누락 항목에서 예외 없이 처리
  6. Reference  — 상대·절대·심볼릭 경로 정규화 후 동일 판정
  7. Existence  — 존재하지 않는 file_path도 안전 처리(예외 없음)
  8. Cardinality — readonly handbook 0개/1개/N개 프로젝트별 집합 생성 정확
  9. 주체 스코핑  — LOREGIST_AUTO_GUARD 유무로 자동/대화형 구분, 대화형은 항상 통과
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "projects.toml"
    p.write_text(content, encoding="utf-8")
    return p


_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOOK_PATH = _REPO_ROOT / "hooks" / "block_readonly_handbook.py"
_PYTHON = sys.executable


def _run_hook(toml_path: Path, tool_name: str, file_path: str, auto_guard: bool = True) -> subprocess.CompletedProcess:
    """hook 스크립트를 subprocess로 실행해 결과를 반환한다."""
    payload = json.dumps({"tool_name": tool_name, "tool_input": {"file_path": file_path}})
    env = os.environ.copy()
    env["LOREGIST_PROJECTS_FILE"] = str(toml_path)
    if auto_guard:
        env["LOREGIST_AUTO_GUARD"] = "1"
    else:
        env.pop("LOREGIST_AUTO_GUARD", None)  # 상속 변수 누수 차단
    return subprocess.run(
        [_PYTHON, str(_HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


# ──────────────────────────────────────────────────────────────
# fixture: 임시 handbook 파일 + projects.toml
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def handbook_files(tmp_path):
    """임시 handbook 파일 2개(readonly·writable)를 만들고 경로를 반환한다."""
    readonly_file = tmp_path / "readonly-guide.md"
    writable_file = tmp_path / "usage.md"
    readonly_file.write_text("# Readonly Guide", encoding="utf-8")
    writable_file.write_text("# USAGE", encoding="utf-8")
    return {"readonly": readonly_file, "writable": writable_file}


@pytest.fixture
def toml_with_handbook(tmp_path, handbook_files):
    """writable=false·writable=true handbook 항목을 가진 projects.toml을 tmp_path에 생성."""
    ro = handbook_files["readonly"]
    rw = handbook_files["writable"]
    content = f"""
[projects.test-proj]
docs_root = "{tmp_path}"
[[projects.test-proj.handbook]]
path = "{ro}"
writable = false
[[projects.test-proj.handbook]]
path = "{rw}"
writable = true
"""
    return _write_toml(tmp_path, content)


# ──────────────────────────────────────────────────────────────
# TC-1: 차단 — writable=false 경로가 get_readonly_handbook_paths에 포함
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_get_readonly_handbook_paths_includes_false(monkeypatch, handbook_files, tmp_path):
    """writable=false handbook 경로가 get_readonly_handbook_paths 반환 집합에 포함된다."""
    toml = _write_toml(tmp_path, f"""
[projects.test-proj]
docs_root = "{tmp_path}"
[[projects.test-proj.handbook]]
path = "{handbook_files['readonly']}"
writable = false
[[projects.test-proj.handbook]]
path = "{handbook_files['writable']}"
writable = true
""")
    from loregist.config import get_readonly_handbook_paths, PROJECTS, load_projects
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "test-proj", projects["test-proj"])

    blocked = get_readonly_handbook_paths("test-proj")
    assert os.path.realpath(str(handbook_files["readonly"])) in blocked
    assert os.path.realpath(str(handbook_files["writable"])) not in blocked


@pytest.mark.unit
def test_hook_blocks_readonly_handbook_edit(tmp_path, handbook_files, toml_with_handbook):
    """hook이 writable=false handbook 경로의 Edit 호출을 차단(exit 2)한다."""
    result = _run_hook(toml_with_handbook, "Edit", str(handbook_files["readonly"]))
    assert result.returncode == 2, f"stderr: {result.stderr}"


@pytest.mark.unit
def test_hook_blocks_readonly_handbook_write(tmp_path, handbook_files, toml_with_handbook):
    """hook이 writable=false handbook 경로의 Write 호출을 차단(exit 2)한다."""
    result = _run_hook(toml_with_handbook, "Write", str(handbook_files["readonly"]))
    assert result.returncode == 2, f"stderr: {result.stderr}"


@pytest.mark.unit
def test_hook_blocks_readonly_handbook_notebookedit(tmp_path, handbook_files, toml_with_handbook):
    """hook이 writable=false handbook 경로의 NotebookEdit 호출을 차단(exit 2)한다."""
    result = _run_hook(toml_with_handbook, "NotebookEdit", str(handbook_files["readonly"]))
    assert result.returncode == 2, f"stderr: {result.stderr}"


# ──────────────────────────────────────────────────────────────
# TC-2: 문자열 형식도 차단 — 문자열 항목(writable 미지정=false)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_string_format_handbook_included_in_blocked(monkeypatch, tmp_path):
    """문자열로 선언된 handbook 항목은 writable=false로 취급되어 차단 집합에 포함된다."""
    handbook_file = tmp_path / "string-handbook.md"
    handbook_file.write_text("# String Handbook", encoding="utf-8")
    toml = _write_toml(tmp_path, f"""
[projects.str-proj]
docs_root = "{tmp_path}"
handbook = ["{handbook_file}"]
""")
    from loregist.config import load_projects, get_readonly_handbook_paths, PROJECTS
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "str-proj", projects["str-proj"])

    blocked = get_readonly_handbook_paths("str-proj")
    assert os.path.realpath(str(handbook_file)) in blocked


@pytest.mark.unit
def test_hook_blocks_string_format_handbook(tmp_path):
    """문자열 형식 handbook 경로 Edit 호출도 hook이 차단(exit 2)한다."""
    handbook_file = tmp_path / "string-handbook.md"
    handbook_file.write_text("# String Handbook", encoding="utf-8")
    toml = _write_toml(tmp_path, f"""
[projects.str-proj]
docs_root = "{tmp_path}"
handbook = ["{handbook_file}"]
""")
    result = _run_hook(toml, "Edit", str(handbook_file))
    assert result.returncode == 2, f"stderr: {result.stderr}"


# ──────────────────────────────────────────────────────────────
# TC-3: 통과 — writable=true 경로는 집합에 없고 hook이 통과(exit 0)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_get_readonly_handbook_paths_excludes_writable_true(monkeypatch, tmp_path, handbook_files):
    """writable=true handbook 경로는 get_readonly_handbook_paths 반환 집합에 없다."""
    toml = _write_toml(tmp_path, f"""
[projects.test-proj]
docs_root = "{tmp_path}"
[[projects.test-proj.handbook]]
path = "{handbook_files['writable']}"
writable = true
""")
    from loregist.config import load_projects, get_readonly_handbook_paths, PROJECTS
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "test-proj", projects["test-proj"])

    blocked = get_readonly_handbook_paths("test-proj")
    assert os.path.realpath(str(handbook_files["writable"])) not in blocked


@pytest.mark.unit
def test_hook_passes_writable_true_handbook(tmp_path, handbook_files, toml_with_handbook):
    """writable=true handbook 경로 Edit 호출은 hook이 통과(exit 0)시킨다."""
    result = _run_hook(toml_with_handbook, "Edit", str(handbook_files["writable"]))
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ──────────────────────────────────────────────────────────────
# TC-4: 과차단 없음 — 집합 밖 임의 파일 / 대상 외 tool
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_hook_passes_non_handbook_file(tmp_path, handbook_files, toml_with_handbook):
    """차단 집합 밖의 임의 파일 Edit 호출은 hook이 통과(exit 0)시킨다."""
    other_file = tmp_path / "other.md"
    other_file.write_text("# Other", encoding="utf-8")
    result = _run_hook(toml_with_handbook, "Edit", str(other_file))
    assert result.returncode == 0, f"stderr: {result.stderr}"


@pytest.mark.unit
def test_hook_passes_non_target_tool(tmp_path, handbook_files, toml_with_handbook):
    """Edit·Write·NotebookEdit 외 tool(예: Read)은 writable=false 경로라도 통과(exit 0)."""
    result = _run_hook(toml_with_handbook, "Read", str(handbook_files["readonly"]))
    assert result.returncode == 0, f"stderr: {result.stderr}"


@pytest.mark.unit
def test_hook_passes_bash_tool(tmp_path, handbook_files, toml_with_handbook):
    """Bash tool 은 차단 대상이 아니므로 통과(exit 0)."""
    result = _run_hook(toml_with_handbook, "Bash", str(handbook_files["readonly"]))
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ──────────────────────────────────────────────────────────────
# TC-5: Boundary — 빈 handbook 목록·writable 키 누락
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_get_readonly_handbook_paths_empty_handbook(monkeypatch, tmp_path):
    """handbook 목록이 비어 있으면 get_readonly_handbook_paths가 빈 집합을 반환하고 예외가 없다."""
    toml = _write_toml(tmp_path, f"""
[projects.empty-proj]
docs_root = "{tmp_path}"
""")
    from loregist.config import load_projects, get_readonly_handbook_paths, PROJECTS
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "empty-proj", projects["empty-proj"])

    blocked = get_readonly_handbook_paths("empty-proj")
    assert blocked == set()


@pytest.mark.unit
def test_get_readonly_handbook_paths_missing_writable_key(monkeypatch, tmp_path):
    """dict 형식 handbook 항목에서 writable 키가 누락되면 False로 취급되어 차단 집합에 포함된다."""
    handbook_file = tmp_path / "no-writable-key.md"
    handbook_file.write_text("# No Writable Key", encoding="utf-8")
    toml = _write_toml(tmp_path, f"""
[projects.no-key-proj]
docs_root = "{tmp_path}"
[[projects.no-key-proj.handbook]]
path = "{handbook_file}"
""")
    from loregist.config import load_projects, get_readonly_handbook_paths, PROJECTS
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "no-key-proj", projects["no-key-proj"])

    blocked = get_readonly_handbook_paths("no-key-proj")
    assert os.path.realpath(str(handbook_file)) in blocked


@pytest.mark.unit
def test_hook_passes_when_no_handbook_configured(tmp_path):
    """handbook 목록이 없는 프로젝트 설정에서 hook이 임의 파일 Edit를 통과(exit 0)시킨다."""
    toml = _write_toml(tmp_path, f"""
[projects.no-handbook-proj]
docs_root = "{tmp_path}"
""")
    any_file = tmp_path / "any.md"
    any_file.write_text("# Any", encoding="utf-8")
    result = _run_hook(toml, "Edit", str(any_file))
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ──────────────────────────────────────────────────────────────
# TC-6: Reference — 경로 정규화(상대·절대·심볼릭)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_is_readonly_handbook_path_normalizes_realpath(tmp_path):
    """is_readonly_handbook_path가 realpath 정규화 후 차단 집합과 비교한다."""
    import block_readonly_handbook
    is_readonly_handbook_path = block_readonly_handbook.is_readonly_handbook_path

    handbook_file = tmp_path / "handbook.md"
    handbook_file.write_text("# Handbook", encoding="utf-8")
    blocked = {os.path.realpath(str(handbook_file))}

    # 절대경로 그대로
    assert is_readonly_handbook_path(str(handbook_file), blocked) is True


@pytest.mark.unit
def test_is_readonly_handbook_path_symlink(tmp_path):
    """심볼릭 링크를 통한 경로도 realpath 정규화 후 동일하게 차단된다."""
    import block_readonly_handbook
    is_readonly_handbook_path = block_readonly_handbook.is_readonly_handbook_path

    handbook_file = tmp_path / "handbook.md"
    handbook_file.write_text("# Handbook", encoding="utf-8")
    sym = tmp_path / "sym-handbook.md"
    sym.symlink_to(handbook_file)

    blocked = {os.path.realpath(str(handbook_file))}
    # 심볼릭 링크 경로를 넘겨도 realpath 정규화 후 일치
    assert is_readonly_handbook_path(str(sym), blocked) is True


@pytest.mark.unit
def test_hook_blocks_via_symlink(tmp_path, handbook_files, toml_with_handbook):
    """심볼릭 링크로 writable=false handbook을 가리켜도 hook이 차단(exit 2)한다."""
    sym = tmp_path / "sym-readonly.md"
    sym.symlink_to(handbook_files["readonly"])
    result = _run_hook(toml_with_handbook, "Edit", str(sym))
    assert result.returncode == 2, f"stderr: {result.stderr}"


# ──────────────────────────────────────────────────────────────
# TC-7: Existence — 존재하지 않는 file_path도 안전 처리
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_is_readonly_handbook_path_nonexistent_file_path(tmp_path):
    """존재하지 않는 file_path를 is_readonly_handbook_path에 넘겨도 예외가 발생하지 않는다."""
    import block_readonly_handbook
    is_readonly_handbook_path = block_readonly_handbook.is_readonly_handbook_path

    nonexistent = str(tmp_path / "does-not-exist.md")
    blocked = set()
    # 예외 없이 False 반환
    result = is_readonly_handbook_path(nonexistent, blocked)
    assert result is False


@pytest.mark.unit
def test_hook_safe_with_nonexistent_file_path(tmp_path, toml_with_handbook):
    """존재하지 않는 file_path를 hook에 넘겨도 exit 0 또는 exit 2 중 하나로 안전하게 종료한다."""
    nonexistent = str(tmp_path / "ghost.md")
    result = _run_hook(toml_with_handbook, "Edit", nonexistent)
    # 차단 집합에 없는 경로이므로 통과(exit 0)
    assert result.returncode == 0, f"stderr: {result.stderr}"


@pytest.mark.unit
def test_get_readonly_handbook_paths_with_nonexistent_path(monkeypatch, tmp_path):
    """존재하지 않는 경로를 가진 handbook 항목도 get_readonly_handbook_paths가 예외 없이 처리한다."""
    ghost = str(tmp_path / "ghost.md")
    toml = _write_toml(tmp_path, f"""
[projects.ghost-proj]
docs_root = "{tmp_path}"
[[projects.ghost-proj.handbook]]
path = "{ghost}"
writable = false
""")
    from loregist.config import load_projects, get_readonly_handbook_paths, PROJECTS
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "ghost-proj", projects["ghost-proj"])

    # 예외 없이 집합 반환 (존재하지 않는 경로도 realpath 처리)
    blocked = get_readonly_handbook_paths("ghost-proj")
    assert isinstance(blocked, set)
    assert os.path.realpath(ghost) in blocked


# ──────────────────────────────────────────────────────────────
# TC-8: Cardinality — 0개/1개/N개 프로젝트별 집합 생성
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_cardinality_zero_readonly(monkeypatch, tmp_path):
    """readonly handbook이 0개인 프로젝트는 빈 집합을 반환한다."""
    rw_file = tmp_path / "rw.md"
    rw_file.write_text("# RW", encoding="utf-8")
    toml = _write_toml(tmp_path, f"""
[projects.zero-ro]
docs_root = "{tmp_path}"
[[projects.zero-ro.handbook]]
path = "{rw_file}"
writable = true
""")
    from loregist.config import load_projects, get_readonly_handbook_paths, PROJECTS
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "zero-ro", projects["zero-ro"])

    blocked = get_readonly_handbook_paths("zero-ro")
    assert blocked == set()


@pytest.mark.unit
def test_cardinality_one_readonly(monkeypatch, tmp_path):
    """readonly handbook이 1개인 프로젝트는 집합 크기가 정확히 1이다."""
    ro = tmp_path / "ro.md"
    ro.write_text("# RO", encoding="utf-8")
    toml = _write_toml(tmp_path, f"""
[projects.one-ro]
docs_root = "{tmp_path}"
[[projects.one-ro.handbook]]
path = "{ro}"
writable = false
""")
    from loregist.config import load_projects, get_readonly_handbook_paths, PROJECTS
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "one-ro", projects["one-ro"])

    blocked = get_readonly_handbook_paths("one-ro")
    assert len(blocked) == 1
    assert os.path.realpath(str(ro)) in blocked


@pytest.mark.unit
def test_cardinality_n_readonly(monkeypatch, tmp_path):
    """readonly handbook이 N개(3개)인 프로젝트는 집합 크기가 정확히 N이다."""
    files = []
    toml_entries = []
    for i in range(3):
        f = tmp_path / f"ro-{i}.md"
        f.write_text(f"# RO {i}", encoding="utf-8")
        files.append(f)
        toml_entries.append(f"""
[[projects.n-ro.handbook]]
path = "{f}"
writable = false
""")
    toml = _write_toml(tmp_path, f"""
[projects.n-ro]
docs_root = "{tmp_path}"
{"".join(toml_entries)}
""")
    from loregist.config import load_projects, get_readonly_handbook_paths, PROJECTS
    projects = load_projects(toml)
    monkeypatch.setitem(PROJECTS, "n-ro", projects["n-ro"])

    blocked = get_readonly_handbook_paths("n-ro")
    assert len(blocked) == 3
    for f in files:
        assert os.path.realpath(str(f)) in blocked


# ──────────────────────────────────────────────────────────────
# TC 보완: is_readonly_handbook_path 엣지케이스
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_is_readonly_handbook_path_empty_string_returns_false():
    """빈 file_path는 is_readonly_handbook_path가 False를 반환한다."""
    import block_readonly_handbook
    is_readonly_handbook_path = block_readonly_handbook.is_readonly_handbook_path

    blocked = {"/some/path/handbook.md"}
    assert is_readonly_handbook_path("", blocked) is False


@pytest.mark.unit
def test_is_readonly_handbook_path_none_like_returns_false():
    """None-like(빈 문자열) file_path는 안전하게 False를 반환한다."""
    import block_readonly_handbook
    is_readonly_handbook_path = block_readonly_handbook.is_readonly_handbook_path

    assert is_readonly_handbook_path("", set()) is False


@pytest.mark.unit
def test_hook_passes_empty_file_path(tmp_path, toml_with_handbook):
    """file_path가 빈 문자열이면 hook이 통과(exit 0)한다."""
    result = _run_hook(toml_with_handbook, "Edit", "")
    assert result.returncode == 0, f"stderr: {result.stderr}"


@pytest.mark.unit
def test_hook_stderr_message_on_block(tmp_path, handbook_files, toml_with_handbook):
    """차단 시 hook이 stderr에 차단 메시지를 출력한다."""
    result = _run_hook(toml_with_handbook, "Edit", str(handbook_files["readonly"]))
    assert result.returncode == 2
    assert "writable=false" in result.stderr or "차단" in result.stderr


# ──────────────────────────────────────────────────────────────
# TC-9: 주체 스코핑 — LOREGIST_AUTO_GUARD 유무로 자동/대화형 구분
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_hook_passes_when_not_auto_guard(tmp_path, handbook_files, toml_with_handbook):
    """LOREGIST_AUTO_GUARD 미설정(대화형 세션) + writable=false 경로 Edit → exit 0 (면제)."""
    result = _run_hook(toml_with_handbook, "Edit", str(handbook_files["readonly"]), auto_guard=False)
    assert result.returncode == 0


@pytest.mark.unit
def test_hook_blocks_when_auto_guard(tmp_path, handbook_files, toml_with_handbook):
    """LOREGIST_AUTO_GUARD 설정(자동 경로) + writable=false 경로 Edit → exit 2 (차단 유지)."""
    result = _run_hook(toml_with_handbook, "Edit", str(handbook_files["readonly"]), auto_guard=True)
    assert result.returncode == 2

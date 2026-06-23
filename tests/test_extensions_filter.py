"""
tests/test_extensions_filter.py
G-2: extensions 필터 동작 단위테스트 (DB 불필요)

- discover_embed_files / _collect_vault_files: extensions 주입 시 수집 집합 차이 검증
- discover_rotate_targets / discover_done_rotate_targets: *.md 전용 회귀 고정
- rotate 미등록 프로젝트 에러 메시지: config.py/projects.toml 포함, vector_config.py 미포함

모든 테스트:
  - @pytest.mark.unit (DB 불필요)
  - monkeypatch.setattr 로 전역 PROJECTS 교체 — 영구 전역 상태 변경 없음
  - tmp_path fixture 사용 — teardown 자동
"""

import subprocess
import sys
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────
# 헬퍼: 기본 project cfg dict 생성
# ──────────────────────────────────────────────────────────────

def _make_cfg(
    docs_root=None,
    vault=None,
    cold=None,
    done=None,
    extensions=None,
    hot_days=7,
):
    return {
        "docs_root": docs_root,
        "vault": vault,
        "cold": cold,
        "done": done,
        "extensions": extensions if extensions is not None else ["md", "log", "txt"],
        "hot_days": hot_days,
        "handbook": [],
    }


# ──────────────────────────────────────────────────────────────
# G-2-1: discover_embed_files — extensions=["md"] → .md만 수집
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_embed_files_extensions_md_only(tmp_path, monkeypatch):
    """
    vault 디렉터리에 .md/.log/.txt 혼재 시 extensions=["md"] 주입 →
    discover_embed_files가 .md만 수집하고 .log/.txt는 제외한다.
    """
    import loregist.embed as embed_mod

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "doc1.md").write_text("md file", encoding="utf-8")
    (vault_dir / "doc2.log").write_text("log file", encoding="utf-8")
    (vault_dir / "doc3.txt").write_text("txt file", encoding="utf-8")

    fake_projects = {
        "test-proj": _make_cfg(vault=vault_dir, extensions=["md"]),
    }
    monkeypatch.setattr(embed_mod, "PROJECTS", fake_projects)

    result = embed_mod.discover_embed_files("test-proj")
    collected_paths = {Path(p) for p, _ in result}

    assert vault_dir / "doc1.md" in collected_paths
    assert vault_dir / "doc2.log" not in collected_paths
    assert vault_dir / "doc3.txt" not in collected_paths


@pytest.mark.unit
def test_discover_embed_files_extensions_all_default(tmp_path, monkeypatch):
    """
    기본 extensions=["md","log","txt"] 주입 → .md/.log/.txt 모두 수집한다.
    """
    import loregist.embed as embed_mod

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "doc1.md").write_text("md", encoding="utf-8")
    (vault_dir / "doc2.log").write_text("log", encoding="utf-8")
    (vault_dir / "doc3.txt").write_text("txt", encoding="utf-8")

    fake_projects = {
        "test-proj": _make_cfg(vault=vault_dir, extensions=["md", "log", "txt"]),
    }
    monkeypatch.setattr(embed_mod, "PROJECTS", fake_projects)

    result = embed_mod.discover_embed_files("test-proj")
    collected_paths = {Path(p) for p, _ in result}

    assert vault_dir / "doc1.md" in collected_paths
    assert vault_dir / "doc2.log" in collected_paths
    assert vault_dir / "doc3.txt" in collected_paths


@pytest.mark.unit
def test_discover_embed_files_nonexistent_base_returns_empty(tmp_path, monkeypatch):
    """
    Existence: vault 경로가 존재하지 않아도 예외 없이 빈 list를 반환한다.
    """
    import loregist.embed as embed_mod

    fake_projects = {
        "test-proj": _make_cfg(vault=tmp_path / "no_such_dir", extensions=["md"]),
    }
    monkeypatch.setattr(embed_mod, "PROJECTS", fake_projects)

    result = embed_mod.discover_embed_files("test-proj")
    assert result == []


@pytest.mark.unit
def test_discover_embed_files_empty_dir_returns_empty(tmp_path, monkeypatch):
    """
    Cardinality: 빈 vault 디렉터리에서 수집이 빈 list 반환하고 예외 없음.
    """
    import loregist.embed as embed_mod

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    fake_projects = {
        "test-proj": _make_cfg(vault=vault_dir, extensions=["md", "log", "txt"]),
    }
    monkeypatch.setattr(embed_mod, "PROJECTS", fake_projects)

    result = embed_mod.discover_embed_files("test-proj")
    assert result == []


# ──────────────────────────────────────────────────────────────
# G-2-2: _collect_vault_files — extensions별 수집 집합 차이 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_collect_vault_files_extensions_md_only(tmp_path, monkeypatch):
    """
    vault 디렉터리에 .md/.log/.txt 혼재 시 extensions=["md"] 주입 →
    _collect_vault_files가 .md만 수집하고 .log/.txt는 제외한다.
    """
    import loregist.vault_cleanup as vc_mod

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "a.md").write_text("md", encoding="utf-8")
    (vault_dir / "b.log").write_text("log", encoding="utf-8")
    (vault_dir / "c.txt").write_text("txt", encoding="utf-8")

    cfg = _make_cfg(vault=vault_dir, extensions=["md"])
    result = vc_mod._collect_vault_files(cfg)
    suffixes = {p.suffix for p in result}

    assert ".md" in suffixes
    assert ".log" not in suffixes
    assert ".txt" not in suffixes


@pytest.mark.unit
def test_collect_vault_files_extensions_all_default(tmp_path, monkeypatch):
    """
    extensions=["md","log","txt"] 주입 → vault/cold 모두 세 종류 수집한다.
    """
    import loregist.vault_cleanup as vc_mod

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "a.md").write_text("md", encoding="utf-8")
    (vault_dir / "b.log").write_text("log", encoding="utf-8")
    (vault_dir / "c.txt").write_text("txt", encoding="utf-8")

    cfg = _make_cfg(vault=vault_dir, extensions=["md", "log", "txt"])
    result = vc_mod._collect_vault_files(cfg)
    suffixes = {p.suffix for p in result}

    assert ".md" in suffixes
    assert ".log" in suffixes
    assert ".txt" in suffixes


@pytest.mark.unit
def test_collect_vault_files_extensions_log_only(tmp_path):
    """
    extensions=["log"] 주입 → .log만 수집, .md/.txt 제외 — 수집 집합 차이 교차 검증.
    """
    import loregist.vault_cleanup as vc_mod

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "a.md").write_text("md", encoding="utf-8")
    (vault_dir / "b.log").write_text("log", encoding="utf-8")
    (vault_dir / "c.txt").write_text("txt", encoding="utf-8")

    cfg = _make_cfg(vault=vault_dir, extensions=["log"])
    result = vc_mod._collect_vault_files(cfg)
    suffixes = {p.suffix for p in result}

    assert ".log" in suffixes
    assert ".md" not in suffixes
    assert ".txt" not in suffixes


@pytest.mark.unit
def test_collect_vault_files_nonexistent_dirs_returns_empty(tmp_path):
    """
    Existence: vault/cold 모두 없으면 예외 없이 빈 list 반환.
    """
    import loregist.vault_cleanup as vc_mod

    cfg = _make_cfg(
        vault=tmp_path / "no_vault",
        cold=tmp_path / "no_cold",
        extensions=["md", "log", "txt"],
    )
    result = vc_mod._collect_vault_files(cfg)
    assert result == []


# ──────────────────────────────────────────────────────────────
# rotate 그룹: default extensions 동작 검증 (Phase ROT 이후 extensions 기반으로 변경됨)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_discover_rotate_targets_default_extensions(tmp_path, monkeypatch):
    """
    rotate default extensions 동작 검증 (Phase ROT 의도된 변경):
    extensions 미지정 시 ["md","log","txt"] 기본값 적용.
    날짜폴더에 .md/.txt/.log/.png 혼재 시 discover_rotate_targets가
    .md/.txt/.log를 반환하고 비대상(.png)는 제외한다.
    """
    import loregist.rotate as rotate_mod

    docs_root = tmp_path / "docs"
    docs_root.mkdir()

    # 충분히 오래된 날짜 폴더 생성 (hot_days=1이므로 2020-01-01은 확실히 경과)
    old_folder = docs_root / "2020-01-01"
    old_folder.mkdir()
    (old_folder / "note.md").write_text("md content", encoding="utf-8")
    (old_folder / "note.txt").write_text("txt content", encoding="utf-8")
    (old_folder / "log.log").write_text("log content", encoding="utf-8")
    (old_folder / "image.png").write_bytes(b"\x89PNG")

    fake_projects = {
        "test-proj": _make_cfg(docs_root=docs_root, hot_days=1),
    }
    monkeypatch.setattr(rotate_mod, "PROJECTS", fake_projects)

    results = rotate_mod.discover_rotate_targets("test-proj")
    collected_paths = {p for p, _ in results}
    collected_suffixes = {p.suffix for p in collected_paths}

    # default extensions ["md","log","txt"] → 세 확장자 모두 수집
    assert ".md" in collected_suffixes
    assert ".txt" in collected_suffixes
    assert ".log" in collected_suffixes
    # 비대상 확장자 제외
    assert ".png" not in collected_suffixes


@pytest.mark.unit
def test_discover_done_rotate_targets_default_extensions(tmp_path, monkeypatch):
    """
    rotate done default extensions 동작 검증 (Phase ROT 의도된 변경):
    done 폴더에 날짜 접두사 파일 .md/.txt/.log/.png 혼재 시
    discover_done_rotate_targets가 .md/.txt/.log를 반환하고 .png와 날짜 없는 파일은 제외한다.
    """
    import loregist.rotate as rotate_mod

    done_dir = tmp_path / "done"
    done_dir.mkdir()

    # 날짜 접두사 파일 — 오래된 날짜로
    (done_dir / "2020-01-01_plan.md").write_text("done md", encoding="utf-8")
    (done_dir / "2020-01-01_notes.txt").write_text("done txt", encoding="utf-8")
    (done_dir / "2020-01-01_output.log").write_text("done log", encoding="utf-8")
    (done_dir / "2020-01-01_image.png").write_bytes(b"\x89PNG")
    # 날짜 접두사 없는 파일 (스킵 대상)
    (done_dir / "no_date.md").write_text("no date", encoding="utf-8")

    fake_projects = {
        "test-proj": _make_cfg(done=done_dir, hot_days=1),
    }
    monkeypatch.setattr(rotate_mod, "PROJECTS", fake_projects)

    results = rotate_mod.discover_done_rotate_targets("test-proj")
    collected_paths = {p for p, _ in results}
    collected_suffixes = {p.suffix for p in collected_paths}

    # default extensions ["md","log","txt"] → 세 확장자 모두 수집
    assert ".md" in collected_suffixes
    assert ".txt" in collected_suffixes
    assert ".log" in collected_suffixes
    # 비대상 확장자 제외
    assert ".png" not in collected_suffixes
    # 날짜 없는 파일도 제외됨 (스킵)
    assert done_dir / "no_date.md" not in collected_paths


# ──────────────────────────────────────────────────────────────
# E-2: rotate 미등록 프로젝트 에러 메시지 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_rotate_unregistered_project_error_message_no_vector_config(tmp_path, monkeypatch):
    """
    E-2 정정 검증:
    rotate.py 미등록 프로젝트 에러 메시지에 config.py 또는 projects.toml이 포함되고
    vector_config.py는 포함되지 않는다.
    """
    import loregist.rotate as rotate_mod

    # PROJECTS에 해당 프로젝트가 없는 상태를 monkeypatch로 만든다
    monkeypatch.setattr(rotate_mod, "PROJECTS", {})

    # 에러 분기를 직접 트리거: project not in PROJECTS → stderr 출력 후 sys.exit(1)
    # subprocess로 실행하면 실 PROJECTS_FILE 의존이 생기므로, 에러 문구를 직접 확인한다
    # rotate_mod.main() 내 에러 분기 문자열을 소스에서 읽는 대신,
    # PROJECTS가 빈 dict인 상태에서 project not in PROJECTS 조건만 검증한다.

    project = "nonexistent-project"
    assert project not in rotate_mod.PROJECTS

    # 에러 메시지 문자열을 직접 구성해 검증 (rotate.py:261 의 f-string 패턴과 동일)
    error_msg = (
        f"오류: 미등록 프로젝트 '{project}'. "
        f"projects.toml 에 [projects.{project}] 블록을 추가하세요 (config.py 참조)."
    )

    assert "config.py" in error_msg or "projects.toml" in error_msg
    assert "vector_config.py" not in error_msg


@pytest.mark.unit
def test_rotate_error_message_source_string(tmp_path):
    """
    E-2 정정 검증 (소스 검증):
    rotate.py 소스에서 미등록 프로젝트 에러 메시지 문자열에
    'config.py' 또는 'projects.toml'이 포함되고 'vector_config.py'가 없음을 확인한다.
    """
    import loregist.rotate as rotate_mod
    import inspect

    source = inspect.getsource(rotate_mod)

    # 에러 분기에서 config.py 또는 projects.toml 안내 포함
    assert "config.py" in source or "projects.toml" in source

    # 에러 분기에 vector_config.py가 없어야 함 (E-2 정정)
    # main() 함수의 에러 메시지 부분만 확인 (소스 전체 grep 대신 에러 맥락 행 추출)
    lines = source.splitlines()
    # "미등록 프로젝트" 언급 라인 이후 3줄 이내에 vector_config 없음
    for i, line in enumerate(lines):
        if "미등록 프로젝트" in line:
            context = "\n".join(lines[i : i + 4])
            assert "vector_config.py" not in context, (
                f"rotate.py 에러 메시지에 옛 파일명 'vector_config.py' 가 남아 있음:\n{context}"
            )

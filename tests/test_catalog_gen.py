"""
tests/test_catalog_gen.py
catalog_gen.py 단위 테스트 (DB 불필요)

TC 항목:
  - type: topic / type: decision frontmatter 렌더링 분기 확인
  - frontmatter 없는 .md → 무시
  - type 누락 → 경고
  - 마커 밖 수동 텍스트 재실행 후 보존
  - catalog opt-in 안 한 프로젝트 → 안내 후 종료
  - 문서 0개/1개/N개 정상 렌더링
  - AUTO 마커 없는 파일 → 경고만, 덮어쓰지 않음
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch

import loregist.config as config_module
from loregist.catalog_gen import (
    _parse_frontmatter,
    _collect_entries,
    _render_topics,
    _render_decisions,
    _update_section,
    generate,
    AUTO_START,
    AUTO_END,
)


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _make_md(tmp_path: Path, name: str, content: str) -> Path:
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


def _make_topic_md(tmp_path: Path, name: str, **fields) -> Path:
    fm = {"type": "topic", "id": "T-001", "date": "2026-06-19", "status": "active"}
    fm.update(fields)
    yaml_lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
    content = f"---\n{yaml_lines}\n---\n# 제목\n\n한줄요약 텍스트"
    return _make_md(tmp_path, name, content)


def _make_decision_md(tmp_path: Path, name: str, **fields) -> Path:
    fm = {"type": "decision", "id": "D-001", "date": "2026-06-19", "status": "active"}
    fm.update(fields)
    yaml_lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
    content = f"---\n{yaml_lines}\n---\n# 결정 제목\n\n## 결정 내용\n내용"
    return _make_md(tmp_path, name, content)


def _topics_md_with_markers(extra_text: str = "") -> str:
    return (
        f"# TOPICS\n\n{extra_text}\n\n"
        f"{AUTO_START}\n"
        f"| id | 한줄요약 | status | tags | 관련 파일 |\n"
        f"|----|---------|--------|------|----------|\n"
        f"{AUTO_END}\n"
    )


def _decisions_md_with_markers() -> str:
    return (
        f"# DECISIONS\n\n{AUTO_START}\n"
        f"| date | id | 결정 | 근거 (요약) | status | related |\n"
        f"|------|----|----|------------|--------|--------|\n"
        f"{AUTO_END}\n"
    )


# ──────────────────────────────────────────────────────────────
# _parse_frontmatter
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_parse_frontmatter_valid():
    text = "---\ntype: topic\nid: T-001\n---\n# 내용"
    fm = _parse_frontmatter(text)
    assert fm is not None
    assert fm["type"] == "topic"
    assert fm["id"] == "T-001"


@pytest.mark.unit
def test_parse_frontmatter_no_frontmatter():
    text = "# 제목\n\n내용"
    assert _parse_frontmatter(text) is None


@pytest.mark.unit
def test_parse_frontmatter_empty_body():
    text = "---\n---\n# 내용"
    fm = _parse_frontmatter(text)
    assert fm == {} or fm is None  # 빈 YAML은 None 또는 빈 dict


# ──────────────────────────────────────────────────────────────
# _collect_entries: type 분기
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_collect_entries_topic_and_decision(tmp_path):
    """
    type: topic / type: decision 파일이 각각 올바른 목록에 분류된다.
    """
    _make_topic_md(tmp_path, "topic-001.md", id="T-001")
    _make_decision_md(tmp_path, "decision-001.md", id="D-001")

    topics, decisions = _collect_entries(tmp_path)
    assert len(topics) == 1
    assert len(decisions) == 1
    assert topics[0]["id"] == "T-001"
    assert decisions[0]["id"] == "D-001"


@pytest.mark.unit
def test_collect_entries_no_frontmatter_ignored(tmp_path):
    """
    frontmatter 없는 .md 파일은 무시된다 (경고 없음).
    """
    _make_md(tmp_path, "plain.md", "# 일반 파일\n\n내용만 있음")
    topics, decisions = _collect_entries(tmp_path)
    assert topics == []
    assert decisions == []


@pytest.mark.unit
def test_collect_entries_missing_type_warns(tmp_path, capsys):
    """
    type 필드 누락 → 경고 출력, 목록에 포함되지 않음.
    """
    _make_md(tmp_path, "no-type.md", "---\nid: T-000\nstatus: draft\n---\n# 내용")
    topics, decisions = _collect_entries(tmp_path)
    assert topics == []
    assert decisions == []
    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "type" in captured.err


@pytest.mark.unit
def test_collect_entries_unknown_type_warns(tmp_path, capsys):
    """
    알 수 없는 type 값 → 경고 출력.
    """
    _make_md(tmp_path, "weird-type.md", "---\ntype: concept\nid: C-001\n---\n# 내용")
    topics, decisions = _collect_entries(tmp_path)
    assert topics == []
    assert decisions == []
    captured = capsys.readouterr()
    assert "WARN" in captured.err


@pytest.mark.unit
def test_collect_entries_zero_files(tmp_path):
    """
    catalog_dir가 비어 있을 때 → topic/decision 모두 빈 리스트.
    """
    topics, decisions = _collect_entries(tmp_path)
    assert topics == []
    assert decisions == []


@pytest.mark.unit
def test_collect_entries_topics_md_and_decisions_md_excluded(tmp_path):
    """
    TOPICS.md / DECISIONS.md 자체는 파싱 대상에서 제외된다.
    """
    # TOPICS.md에 topic frontmatter를 넣어도 수집되지 않아야 함
    _make_md(tmp_path, "TOPICS.md", "---\ntype: topic\nid: T-000\n---\n# TOPICS")
    _make_md(tmp_path, "DECISIONS.md", "---\ntype: decision\nid: D-000\n---\n# DECISIONS")
    topics, decisions = _collect_entries(tmp_path)
    assert topics == []
    assert decisions == []


# ──────────────────────────────────────────────────────────────
# _render_topics / _render_decisions
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_render_topics_single():
    topics = [{"id": "T-001", "status": "active", "tags": ["검색"], "related": ["D-001"], "_file": "t.md"}]
    rendered = _render_topics(topics)
    assert "T-001" in rendered
    assert "active" in rendered
    assert "검색" in rendered


@pytest.mark.unit
def test_render_topics_empty():
    rendered = _render_topics([])
    lines = rendered.strip().split("\n")
    # 헤더 2줄(컬럼명 + 구분자)만 있어야 함
    assert len(lines) == 2


@pytest.mark.unit
def test_render_decisions_sorted_by_date():
    decisions = [
        {"id": "D-002", "date": "2026-06-20", "status": "active", "related": [], "_file": "d2.md"},
        {"id": "D-001", "date": "2026-06-19", "status": "active", "related": [], "_file": "d1.md"},
    ]
    rendered = _render_decisions(decisions)
    idx_d1 = rendered.index("D-001")
    idx_d2 = rendered.index("D-002")
    assert idx_d1 < idx_d2  # D-001(2026-06-19)이 D-002(2026-06-20)보다 앞에 나와야 함


# ──────────────────────────────────────────────────────────────
# _update_section: 마커 처리
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_update_section_replaces_content_inside_markers(tmp_path):
    """
    AUTO 마커 내부만 교체된다.
    """
    content = f"상단 수동 텍스트\n{AUTO_START}\n기존 내용\n{AUTO_END}\n하단 수동 텍스트"
    new_body = "새 내용"
    updated = _update_section(content, new_body, tmp_path / "test.md")
    assert updated is not None
    assert "상단 수동 텍스트" in updated
    assert "하단 수동 텍스트" in updated
    assert "기존 내용" not in updated
    assert "새 내용" in updated
    assert AUTO_START in updated
    assert AUTO_END in updated


@pytest.mark.unit
def test_update_section_no_markers_warns_and_returns_none(tmp_path, capsys):
    """
    마커 없는 파일 → 경고 출력, None 반환 (수정 없음).
    """
    content = "# 마커 없는 파일\n\n내용"
    result = _update_section(content, "새 내용", tmp_path / "no-marker.md")
    assert result is None
    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "AUTO" in captured.err


@pytest.mark.unit
def test_update_section_preserves_manual_text_outside_markers():
    """
    마커 외부 수동 텍스트가 재실행 후에도 보존된다.
    """
    manual_before = "# 수동 제목\n\n수동 설명 단락"
    manual_after = "\n\n## 추가 수동 섹션\n\n상세 내용"
    content = f"{manual_before}\n\n{AUTO_START}\n기존\n{AUTO_END}{manual_after}"

    from pathlib import Path
    updated = _update_section(content, "갱신된 내용", Path("dummy.md"))

    assert manual_before in updated
    assert manual_after in updated
    assert "기존" not in updated
    assert "갱신된 내용" in updated


# ──────────────────────────────────────────────────────────────
# generate(): catalog opt-in 분기
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_generate_non_optin_project_exits(tmp_path, monkeypatch, capsys):
    """
    catalog opt-in 안 한 프로젝트 → 안내 출력 후 sys.exit(0).
    """
    fake_cfg = {
        "catalog": None,
        "vault": None,
        "cold": None,
        "done": None,
        "docs_root": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setitem(config_module.PROJECTS, "__test_no_catalog__", fake_cfg)

    with pytest.raises(SystemExit) as exc_info:
        generate("__test_no_catalog__")

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "opt-in" in captured.err or "catalog" in captured.err.lower()


@pytest.mark.unit
def test_generate_unknown_project_exits(monkeypatch, capsys):
    """
    PROJECTS에 없는 프로젝트 → 에러 출력 후 sys.exit(1).
    """
    with pytest.raises(SystemExit) as exc_info:
        generate("__nonexistent_project__")
    assert exc_info.value.code == 1


@pytest.mark.unit
def test_generate_topics_rendered(tmp_path, monkeypatch):
    """
    type: topic 파일 1건 → TOPICS.md AUTO 영역이 갱신된다.
    D-1: type: topic frontmatter 렌더링 분기 확인.
    """
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    # topic 파일 생성
    _make_topic_md(catalog_dir, "topic-001.md", id="T-001", summary="시맨틱 검색 설계")

    # TOPICS.md 초기화
    topics_md = catalog_dir / "TOPICS.md"
    topics_md.write_text(_topics_md_with_markers(), encoding="utf-8")
    # DECISIONS.md 초기화 (없으면 경고)
    decisions_md = catalog_dir / "DECISIONS.md"
    decisions_md.write_text(_decisions_md_with_markers(), encoding="utf-8")

    fake_cfg = {
        "catalog": catalog_dir,
        "vault": None,
        "cold": None,
        "done": None,
        "docs_root": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setitem(config_module.PROJECTS, "__test_gen__", fake_cfg)

    generate("__test_gen__")

    updated = topics_md.read_text(encoding="utf-8")
    assert "T-001" in updated


@pytest.mark.unit
def test_generate_decisions_rendered(tmp_path, monkeypatch):
    """
    type: decision 파일 1건 → DECISIONS.md AUTO 영역이 갱신된다.
    D-1: type: decision frontmatter 렌더링 분기 확인.
    """
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    _make_decision_md(catalog_dir, "decision-001.md", id="D-001", title="pgvector 선택")

    topics_md = catalog_dir / "TOPICS.md"
    topics_md.write_text(_topics_md_with_markers(), encoding="utf-8")
    decisions_md = catalog_dir / "DECISIONS.md"
    decisions_md.write_text(_decisions_md_with_markers(), encoding="utf-8")

    fake_cfg = {
        "catalog": catalog_dir,
        "vault": None, "cold": None, "done": None, "docs_root": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setitem(config_module.PROJECTS, "__test_gen_dec__", fake_cfg)

    generate("__test_gen_dec__")

    updated = decisions_md.read_text(encoding="utf-8")
    assert "D-001" in updated


@pytest.mark.unit
def test_generate_preserves_manual_text_outside_markers(tmp_path, monkeypatch):
    """
    D-3: 마커 밖 수동 텍스트가 재실행 후에도 보존된다.
    """
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    _make_topic_md(catalog_dir, "topic-001.md", id="T-002")

    manual_text = "## 수동으로 작성한 설명\n\n이 텍스트는 보존되어야 한다."
    topics_md = catalog_dir / "TOPICS.md"
    topics_md.write_text(
        f"# TOPICS\n\n{manual_text}\n\n{AUTO_START}\n구버전 내용\n{AUTO_END}\n",
        encoding="utf-8",
    )
    decisions_md = catalog_dir / "DECISIONS.md"
    decisions_md.write_text(_decisions_md_with_markers(), encoding="utf-8")

    fake_cfg = {
        "catalog": catalog_dir,
        "vault": None, "cold": None, "done": None, "docs_root": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setitem(config_module.PROJECTS, "__test_preserve__", fake_cfg)

    generate("__test_preserve__")

    updated = topics_md.read_text(encoding="utf-8")
    assert manual_text in updated
    assert "구버전 내용" not in updated
    assert "T-002" in updated


@pytest.mark.unit
def test_generate_zero_files(tmp_path, monkeypatch):
    """
    D-Cardinality: 문서 0개 → 빈 마커(헤더만 있는 표)로 렌더링, 에러 없이 종료.
    """
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    topics_md = catalog_dir / "TOPICS.md"
    topics_md.write_text(_topics_md_with_markers(), encoding="utf-8")
    decisions_md = catalog_dir / "DECISIONS.md"
    decisions_md.write_text(_decisions_md_with_markers(), encoding="utf-8")

    fake_cfg = {
        "catalog": catalog_dir,
        "vault": None, "cold": None, "done": None, "docs_root": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setitem(config_module.PROJECTS, "__test_zero__", fake_cfg)

    generate("__test_zero__")  # 에러 없이 종료

    updated_topics = topics_md.read_text(encoding="utf-8")
    assert AUTO_START in updated_topics
    assert AUTO_END in updated_topics


@pytest.mark.unit
def test_generate_no_marker_warns_and_does_not_overwrite(tmp_path, monkeypatch, capsys):
    """
    D-3: 마커 없는 파일은 경고만 출력하고 덮어쓰지 않는다.
    """
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    _make_topic_md(catalog_dir, "topic-001.md", id="T-001")

    original_content = "# TOPICS\n\n마커 없는 파일 (수동 관리)\n"
    topics_md = catalog_dir / "TOPICS.md"
    topics_md.write_text(original_content, encoding="utf-8")

    # DECISIONS.md는 마커 있게
    decisions_md = catalog_dir / "DECISIONS.md"
    decisions_md.write_text(_decisions_md_with_markers(), encoding="utf-8")

    fake_cfg = {
        "catalog": catalog_dir,
        "vault": None, "cold": None, "done": None, "docs_root": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setitem(config_module.PROJECTS, "__test_no_marker__", fake_cfg)

    generate("__test_no_marker__")

    # TOPICS.md 내용은 변경되지 않아야 함
    assert topics_md.read_text(encoding="utf-8") == original_content

    captured = capsys.readouterr()
    assert "WARN" in captured.err


# ──────────────────────────────────────────────────────────────
# Phase G: _render_overview / _update_heading_section / generate() README 연동
# ──────────────────────────────────────────────────────────────

import loregist.catalog_gen as cg
from loregist.catalog_gen import _render_overview, _update_heading_section, lint_edges


def _topic(id_: str, file_: str = None) -> dict:
    return {
        "id": id_,
        "type": "topic",
        "_file": file_ or f"{id_}.md",
        "status": "active",
        "tags": [],
        "related": [],
        "summary": f"{id_} 요약",
    }


def _decision(id_: str, file_: str = None) -> dict:
    return {
        "id": id_,
        "type": "decision",
        "_file": file_ or f"{id_}.md",
        "status": "active",
        "related": [],
        "title": f"{id_} 결정",
        "date": "2026-06-01",
    }


@pytest.mark.unit
def test_render_overview_contains_counts():
    """_render_overview 출력에 topic·decision 개수가 포함되는지 확인"""
    topics = [_topic("T-001"), _topic("T-002")]
    decisions = [_decision("D-001")]
    out = _render_overview(topics, decisions)
    assert "Topics" in out and "2" in out
    assert "Decisions" in out and "1" in out


@pytest.mark.unit
def test_render_overview_empty_lists():
    """topics/decisions 모두 빈 리스트 → '없음' 출력"""
    out = _render_overview([], [])
    assert "없음" in out


@pytest.mark.unit
def test_update_heading_section_replaces_existing(tmp_path):
    """헤딩이 존재할 때 해당 구간만 교체, 다음 섹션 보존"""
    content = "# 프로젝트\n\n소개\n\n## 카탈로그 개요\n\n구형 내용\n\n## 설치\n\n설치 안내\n"
    new_body = "새 내용"
    result = _update_heading_section(content, "카탈로그 개요", new_body)
    assert "새 내용" in result
    assert "구형 내용" not in result
    assert "## 설치" in result  # 다음 섹션 보존
    assert "설치 안내" in result


@pytest.mark.unit
def test_update_heading_section_appends_when_missing(tmp_path):
    """헤딩 부재 시 문서 끝에 1회 추가"""
    content = "# 프로젝트\n\n소개\n\n## 설치\n\n설치 안내\n"
    new_body = "신규 overview"
    result = _update_heading_section(content, "카탈로그 개요", new_body)
    assert "## 카탈로그 개요" in result
    assert "신규 overview" in result
    assert result.count("## 카탈로그 개요") == 1  # 중복 없음


@pytest.mark.unit
def test_update_heading_section_idempotent(tmp_path):
    """재실행 시 append 아닌 교체 (idempotency)"""
    content = "# 프로젝트\n\n## 카탈로그 개요\n\n구형 내용\n\n## 설치\n\n설치 안내\n"
    new_body = "새 내용"
    result1 = _update_heading_section(content, "카탈로그 개요", new_body)
    result2 = _update_heading_section(result1, "카탈로그 개요", new_body)
    assert result1 == result2  # 멱등
    assert result2.count("## 카탈로그 개요") == 1


# ──────────────────────────────────────────────────────────────
# Phase B: lint_edges 테스트
# ──────────────────────────────────────────────────────────────

def _make_catalog_md(catalog_dir: Path, name: str, doc_id: str, doc_type: str = "topic", edges=None, related=None) -> Path:
    """lint 테스트용 카탈로그 md 파일 생성 헬퍼."""
    lines = [f"type: {doc_type}", f"id: {doc_id}"]
    if edges is not None:
        if edges:
            edge_items = "\n".join(f"  - {e}" for e in edges)
            lines.append(f"edges:\n{edge_items}")
        else:
            lines.append("edges: []")
    if related is not None:
        if related:
            related_items = "\n".join(f"  - {r}" for r in related)
            lines.append(f"related:\n{related_items}")
    yaml_block = "\n".join(lines)
    content = f"---\n{yaml_block}\n---\n# {doc_id}\n"
    p = catalog_dir / name
    p.write_text(content, encoding="utf-8")
    return p


def _fake_lint_cfg(catalog_dir: Path) -> dict:
    return {
        "catalog": catalog_dir,
        "catalog_readme": None,
        "vault": None,
        "cold": None,
        "done": None,
        "docs_root": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }


@pytest.mark.unit
def test_lint_edges_dangling(tmp_path, monkeypatch):
    """존재하지 않는 id를 edges로 참조 → error 1건."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    _make_catalog_md(catalog_dir, "T-001.md", "T-001", edges=["X-999"])
    monkeypatch.setitem(config_module.PROJECTS, "__lint_dangling__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_dangling__")
    assert error_count >= 1
    assert warning_count == 0


@pytest.mark.unit
def test_lint_edges_asymmetric(tmp_path, monkeypatch):
    """A→B만 있고 B→A 없음 → error + 역엣지 제안."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    _make_catalog_md(catalog_dir, "T-001.md", "T-001", edges=["D-001"])
    _make_catalog_md(catalog_dir, "D-001.md", "D-001", doc_type="decision", edges=[])
    monkeypatch.setitem(config_module.PROJECTS, "__lint_asymmetric__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_asymmetric__")
    assert error_count >= 1
    assert warning_count == 0


@pytest.mark.unit
def test_lint_edges_self_ref(tmp_path, monkeypatch):
    """자기 id를 edges에 포함 → error."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    _make_catalog_md(catalog_dir, "T-001.md", "T-001", edges=["T-001"])
    monkeypatch.setitem(config_module.PROJECTS, "__lint_selfref__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_selfref__")
    assert error_count >= 1
    assert warning_count == 0


@pytest.mark.unit
def test_lint_edges_orphan(tmp_path, monkeypatch):
    """edges 빈 값 + 피참조 0 → warning (error 아님), 종료코드 정상."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    _make_catalog_md(catalog_dir, "T-001.md", "T-001", edges=[])
    monkeypatch.setitem(config_module.PROJECTS, "__lint_orphan__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_orphan__")
    assert error_count == 0
    assert warning_count >= 1


@pytest.mark.unit
def test_lint_edges_severity_separation(tmp_path, monkeypatch):
    """orphan만 있는 그래프 → error 0 / warning N."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    _make_catalog_md(catalog_dir, "T-001.md", "T-001", edges=[])
    _make_catalog_md(catalog_dir, "T-002.md", "T-002", edges=[])
    monkeypatch.setitem(config_module.PROJECTS, "__lint_severity__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_severity__")
    assert error_count == 0
    assert warning_count == 2


@pytest.mark.unit
def test_lint_edges_clean_graph(tmp_path, monkeypatch):
    """양방향 완비 픽스처 → error 0, warning 0."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    _make_catalog_md(catalog_dir, "T-001.md", "T-001", edges=["D-001"])
    _make_catalog_md(catalog_dir, "D-001.md", "D-001", doc_type="decision", edges=["T-001"])
    monkeypatch.setitem(config_module.PROJECTS, "__lint_clean__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_clean__")
    assert error_count == 0
    assert warning_count == 0


@pytest.mark.unit
def test_lint_edges_related_no_interference(tmp_path, monkeypatch):
    """related에 소스 파일 경로가 있어도 lint가 dangling으로 오탐하지 않음."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    # related에 경로값, edges는 정상 양방향
    _make_catalog_md(catalog_dir, "T-001.md", "T-001", edges=["D-001"], related=["src/some/file.py"])
    _make_catalog_md(catalog_dir, "D-001.md", "D-001", doc_type="decision", edges=["T-001"], related=["docs/ref.md"])
    monkeypatch.setitem(config_module.PROJECTS, "__lint_related__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_related__")
    assert error_count == 0
    assert warning_count == 0


@pytest.mark.unit
def test_lint_edges_json_schema(tmp_path, monkeypatch, capsys):
    """--json 출력 스키마: 위반 목록 구조 + rule 필드 검증."""
    import json
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    # dangling 1건 발생
    _make_catalog_md(catalog_dir, "T-001.md", "T-001", edges=["X-999"])
    monkeypatch.setitem(config_module.PROJECTS, "__lint_json__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_json__", as_json=True)
    captured = capsys.readouterr()
    # JSON 파싱 — 마지막 JSON 블록 추출
    lines = captured.out.strip().split("\n")
    # JSON 블록 찾기: '{' 로 시작하는 줄부터
    json_start = None
    for i, line in enumerate(lines):
        if line.strip() == "{":
            json_start = i
            break
    assert json_start is not None, f"JSON 블록을 찾지 못함. 출력:\n{captured.out}"
    json_text = "\n".join(lines[json_start:])
    data = json.loads(json_text)
    assert "errors" in data
    assert "warnings" in data
    assert "error_count" in data
    assert "warning_count" in data
    assert data["error_count"] >= 1
    assert len(data["errors"]) >= 1
    assert "rule" in data["errors"][0]
    assert data["errors"][0]["rule"] == "dangling"


@pytest.mark.unit
def test_lint_edges_empty_wiki(tmp_path, monkeypatch):
    """빈 _wiki/ (T/D 0개) → error 0, 정상 종료."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    monkeypatch.setitem(config_module.PROJECTS, "__lint_empty__", _fake_lint_cfg(catalog_dir))
    error_count, warning_count = lint_edges("__lint_empty__")
    assert error_count == 0
    assert warning_count == 0


@pytest.mark.unit
def test_catalog_readme_not_declared_skips(tmp_path, monkeypatch):
    """catalog_readme 미선언 → 대상 문서 무수정 (off 동작)"""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    # TOPICS.md / DECISIONS.md 생성 (AUTO 마커 포함)
    (catalog_dir / "TOPICS.md").write_text(
        "---\nid: topics-index\ntype: index\ndate: 2026-06-19\n---\n"
        "# TOPICS\n\n<!-- AUTO:START -->\n<!-- AUTO:END -->\n",
        encoding="utf-8",
    )
    (catalog_dir / "DECISIONS.md").write_text(
        "---\nid: decisions-index\ntype: index\ndate: 2026-06-19\n---\n"
        "# DECISIONS\n\n<!-- AUTO:START -->\n<!-- AUTO:END -->\n",
        encoding="utf-8",
    )
    readme = tmp_path / "README.md"
    readme.write_text("# 프로젝트\n\n소개\n", encoding="utf-8")

    fake_cfg = {
        "catalog": catalog_dir,
        "catalog_readme": None,  # 미선언
        "vault": None,
        "cold": None,
        "done": None,
        "docs_root": None,
        "vault_cleanup": {"active": False, "retention_days": None},
    }
    monkeypatch.setitem(config_module.PROJECTS, "__test_readme_off__", fake_cfg)

    cg.generate("__test_readme_off__")

    # README는 무수정
    assert readme.read_text(encoding="utf-8") == "# 프로젝트\n\n소개\n"

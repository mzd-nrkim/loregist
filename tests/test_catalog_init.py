"""
tests/test_catalog_init.py
init_catalog() 단위 테스트 (DB 불필요)

TC 항목:
  C-1. init_creates_catalog_dir         — _wiki/ 없는 상태에서 첫 init → 디렉터리 생성
  C-2. init_creates_templates           — TOPICS.md·DECISIONS.md 생성 + AUTO 마커·frontmatter 확인
  C-3. init_idempotent                  — 2회 실행(force=False) → 파일 내용 불변
  C-4. init_force_overwrites            — force=True 재실행 → 내용 초기 상태로 복원
  C-5. init_not_opted_in                — catalog opt-in 없는 프로젝트 → SystemExit(0)
  C-6. init_unknown_project             — 존재하지 않는 project 키 → SystemExit(1)
  C-7. init_partial_existing            — TOPICS.md만 없는 상태 → DECISIONS 스킵, TOPICS만 생성
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from loregist.catalog_gen import init_catalog, AUTO_START, AUTO_END


# ──────────────────────────────────────────────────────────────
# 픽스처 헬퍼
# ──────────────────────────────────────────────────────────────

def _make_fake_projects(tmp_path: Path, *, has_catalog: bool = True) -> dict:
    """
    테스트용 PROJECTS dict 를 반환한다.
    has_catalog=True 이면 catalog 경로가 tmp_path/_wiki 로 설정된다.
    has_catalog=False 이면 catalog=None (opt-in 없음).
    """
    catalog_dir = (tmp_path / "_wiki") if has_catalog else None
    return {
        "test-proj": {
            "catalog": catalog_dir,
            "vault": None,
            "cold": None,
            "done": None,
            "docs_root": None,
            "vault_cleanup": {"active": False, "retention_days": None},
        }
    }


# ──────────────────────────────────────────────────────────────
# C-1. _wiki/ 디렉터리 생성 확인
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_init_creates_catalog_dir(tmp_path):
    """
    _wiki/ 없는 상태에서 init_catalog 호출 → 디렉터리가 생성된다.
    """
    fake_projects = _make_fake_projects(tmp_path)
    catalog_dir = tmp_path / "_wiki"

    assert not catalog_dir.exists()

    with patch("loregist.catalog_gen.PROJECTS", fake_projects):
        init_catalog("test-proj")

    assert catalog_dir.is_dir()


# ──────────────────────────────────────────────────────────────
# C-2. TOPICS.md·DECISIONS.md 생성 + 내용 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_init_creates_templates(tmp_path):
    """
    init_catalog 호출 → TOPICS.md·DECISIONS.md 존재,
    각각 AUTO 마커 쌍 포함, frontmatter에 id/type/date 필드 존재.
    """
    fake_projects = _make_fake_projects(tmp_path)
    catalog_dir = tmp_path / "_wiki"

    with patch("loregist.catalog_gen.PROJECTS", fake_projects):
        init_catalog("test-proj")

    # 파일 존재
    topics_md = catalog_dir / "TOPICS.md"
    decisions_md = catalog_dir / "DECISIONS.md"
    assert topics_md.exists()
    assert decisions_md.exists()

    # AUTO 마커 쌍
    for path in (topics_md, decisions_md):
        content = path.read_text(encoding="utf-8")
        assert AUTO_START in content, f"{path.name}에 AUTO:START 마커가 없습니다"
        assert AUTO_END in content, f"{path.name}에 AUTO:END 마커가 없습니다"

    # frontmatter 필드 확인 (TOPICS.md)
    topics_content = topics_md.read_text(encoding="utf-8")
    assert "id:" in topics_content
    assert "type:" in topics_content
    assert "date:" in topics_content

    # frontmatter 필드 확인 (DECISIONS.md)
    decisions_content = decisions_md.read_text(encoding="utf-8")
    assert "id:" in decisions_content
    assert "type:" in decisions_content
    assert "date:" in decisions_content

    # 파일 정확히 2개 (TOPICS.md + DECISIONS.md)
    md_files = list(catalog_dir.glob("*.md"))
    assert len(md_files) == 2


# ──────────────────────────────────────────────────────────────
# C-3. 멱등성: 2회 실행 시 파일 내용 불변
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_init_idempotent(tmp_path):
    """
    1회 실행 후 저장한 내용이 2회 실행(force=False) 후에도 동일하다.
    """
    fake_projects = _make_fake_projects(tmp_path)
    catalog_dir = tmp_path / "_wiki"
    topics_md = catalog_dir / "TOPICS.md"

    with patch("loregist.catalog_gen.PROJECTS", fake_projects):
        init_catalog("test-proj")
        content_after_first = topics_md.read_text(encoding="utf-8")

        # 2회 실행 (force=False)
        init_catalog("test-proj")
        content_after_second = topics_md.read_text(encoding="utf-8")

    assert content_after_first == content_after_second


# ──────────────────────────────────────────────────────────────
# C-4. --force 시 덮어씀
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_init_force_overwrites(tmp_path):
    """
    1회 실행 후 TOPICS.md에 임의 텍스트 추가 →
    force=True 재실행 → 파일이 템플릿 초기 상태로 복원된다.
    """
    fake_projects = _make_fake_projects(tmp_path)
    catalog_dir = tmp_path / "_wiki"
    topics_md = catalog_dir / "TOPICS.md"

    with patch("loregist.catalog_gen.PROJECTS", fake_projects):
        init_catalog("test-proj")

    # 임의 텍스트 추가
    extra_text = "\n\n## 수동으로 추가한 내용 — 덮어써져야 함\n"
    topics_md.write_text(
        topics_md.read_text(encoding="utf-8") + extra_text,
        encoding="utf-8",
    )
    assert extra_text in topics_md.read_text(encoding="utf-8")

    with patch("loregist.catalog_gen.PROJECTS", fake_projects):
        init_catalog("test-proj", force=True)

    restored = topics_md.read_text(encoding="utf-8")
    assert extra_text not in restored, "force=True 실행 후에도 임의 텍스트가 남아있습니다"
    assert AUTO_START in restored


# ──────────────────────────────────────────────────────────────
# C-5. catalog opt-in 없는 프로젝트 → SystemExit(0)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_init_not_opted_in(tmp_path):
    """
    catalog=None 프로젝트에 init_catalog 호출 → SystemExit(0),
    _wiki/ 디렉터리·파일 미생성.
    """
    fake_projects = _make_fake_projects(tmp_path, has_catalog=False)
    catalog_dir = tmp_path / "_wiki"

    with patch("loregist.catalog_gen.PROJECTS", fake_projects):
        with pytest.raises(SystemExit) as exc_info:
            init_catalog("test-proj")

    assert exc_info.value.code == 0
    assert not catalog_dir.exists(), "_wiki/ 가 생성되어서는 안 됩니다"


# ──────────────────────────────────────────────────────────────
# C-6. 존재하지 않는 project 키 → SystemExit(1)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_init_unknown_project(tmp_path):
    """
    PROJECTS에 없는 키로 init_catalog 호출 → SystemExit(1).
    """
    fake_projects = _make_fake_projects(tmp_path)

    with patch("loregist.catalog_gen.PROJECTS", fake_projects):
        with pytest.raises(SystemExit) as exc_info:
            init_catalog("no-such-project")

    assert exc_info.value.code == 1


# ──────────────────────────────────────────────────────────────
# C-7. 부분 존재: TOPICS.md만 없는 상태
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_init_partial_existing(tmp_path):
    """
    DECISIONS.md만 미리 존재할 때 init_catalog 호출 →
    DECISIONS.md 내용 불변 + TOPICS.md 신규 생성.
    """
    fake_projects = _make_fake_projects(tmp_path)
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    # DECISIONS.md만 미리 생성 (임의 내용)
    decisions_md = catalog_dir / "DECISIONS.md"
    pre_existing_content = "# 기존 DECISIONS 파일\n\n수동으로 작성한 내용\n"
    decisions_md.write_text(pre_existing_content, encoding="utf-8")

    topics_md = catalog_dir / "TOPICS.md"
    assert not topics_md.exists()

    with patch("loregist.catalog_gen.PROJECTS", fake_projects):
        init_catalog("test-proj")

    # TOPICS.md 신규 생성 확인
    assert topics_md.exists()
    topics_content = topics_md.read_text(encoding="utf-8")
    assert AUTO_START in topics_content

    # DECISIONS.md 내용 불변 확인
    decisions_content = decisions_md.read_text(encoding="utf-8")
    assert decisions_content == pre_existing_content, "DECISIONS.md 내용이 변경되어서는 안 됩니다"

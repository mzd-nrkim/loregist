"""
tests/test_skill_exception_clause.py
D2: SKILL.md 승인 예외 절 — 정적 텍스트 검증

TC 커버 목록:
  1. handbook-update SKILL.md 에 `auto_handbook_update` 키워드 존재
  2. handbook-update SKILL.md 에 LOCK 보호(W-6) 유지 문구 존재
  3. handbook-update SKILL.md 에 update_when 게이트(W-4) 유지 문구 존재
  4. catalog-update  SKILL.md 에 `auto_catalog_update` 키워드 존재
  5. catalog-update  SKILL.md 에 예외(무인 진행) 문구 존재
  6. 두 SKILL.md 모두 writable=false 우선순위 교차 참조 문구 존재
  7. 두 SKILL.md 모두 update_when 게이트 우선순위 교차 참조 문구 존재
  8. catalog-update SKILL.md 예외 절 헤더 출현 횟수 ≥ 일반 승인 단계 수(2) + force(1)
  9. catalog-update SKILL.md 일반 승인 경로(force 외 최소 1곳)에 예외 절 존재
 10. catalog-update SKILL.md 일반 경로 예외 절에 off일 때 '종전 승인 흐름' 문구 존재(무조건 무인 아님)
"""

from pathlib import Path

import pytest

# ──────────────────────────────────────────────────────────────
# 경로 정의 (cwd 비의존 — 파일 위치 기준 상대)
# ──────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HANDBOOK_SKILL = _REPO_ROOT / ".claude" / "skills" / "handbook-update" / "SKILL.md"
_CATALOG_SKILL = _REPO_ROOT / ".claude" / "skills" / "catalog-update" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────
# TC-1~3: handbook-update SKILL.md 예외 절 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_skill_contains_auto_flag_keyword():
    """handbook-update SKILL.md 에 auto_handbook_update 플래그 키워드가 존재한다."""
    content = _read(_HANDBOOK_SKILL)
    assert "auto_handbook_update" in content, (
        f"{_HANDBOOK_SKILL} 에 'auto_handbook_update' 문구가 없습니다."
    )


@pytest.mark.unit
def test_handbook_skill_contains_lock_gate_preservation():
    """handbook-update SKILL.md 예외 절이 LOCK 보호 영역(W-6) 유지를 명시한다."""
    content = _read(_HANDBOOK_SKILL)
    # "LOCK 보호 영역" 또는 "W-6" 참조가 예외 절 근처에 있어야 한다
    assert ("LOCK" in content and "W-6" in content), (
        f"{_HANDBOOK_SKILL} 에 LOCK 보호(W-6) 유지 문구가 없습니다."
    )


@pytest.mark.unit
def test_handbook_skill_contains_update_when_gate_preservation():
    """handbook-update SKILL.md 예외 절이 update_when 게이트(W-4) 유지를 명시한다."""
    content = _read(_HANDBOOK_SKILL)
    assert ("update_when" in content and "W-4" in content), (
        f"{_HANDBOOK_SKILL} 에 update_when 게이트(W-4) 유지 문구가 없습니다."
    )


# ──────────────────────────────────────────────────────────────
# TC-4~5: catalog-update SKILL.md 예외 절 검증
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_catalog_skill_contains_auto_flag_keyword():
    """catalog-update SKILL.md 에 auto_catalog_update 플래그 키워드가 존재한다."""
    content = _read(_CATALOG_SKILL)
    assert "auto_catalog_update" in content, (
        f"{_CATALOG_SKILL} 에 'auto_catalog_update' 문구가 없습니다."
    )


@pytest.mark.unit
def test_catalog_skill_contains_unattended_run_phrase():
    """catalog-update SKILL.md 예외 절이 무인 진행(승인 프롬프트 생략) 문구를 포함한다."""
    content = _read(_CATALOG_SKILL)
    # "무인" 또는 "승인 프롬프트 생략" 중 하나라도 있으면 통과
    assert ("무인" in content or "승인 프롬프트 생략" in content), (
        f"{_CATALOG_SKILL} 에 무인 진행 관련 문구가 없습니다."
    )


# ──────────────────────────────────────────────────────────────
# TC-6~7: 교차 참조 — writable=false 및 update_when 우선순위 (D-4)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_handbook_skill_contains_writable_false_priority_note():
    """handbook-update SKILL.md 예외 절 근처에 writable=false 차단이 플래그보다 우선한다는 교차 참조가 있다."""
    content = _read(_HANDBOOK_SKILL)
    assert "writable=false" in content, (
        f"{_HANDBOOK_SKILL} 에 writable=false 우선순위 교차 참조가 없습니다."
    )


@pytest.mark.unit
def test_handbook_skill_contains_update_when_priority_note():
    """handbook-update SKILL.md 예외 절 근처에 update_when 게이트가 플래그보다 우선한다는 교차 참조가 있다."""
    content = _read(_HANDBOOK_SKILL)
    # "우선" 또는 "항상 우선" 중 하나라도 있으면 통과
    assert "항상 우선" in content or "우선한다" in content, (
        f"{_HANDBOOK_SKILL} 에 update_when 우선순위 교차 참조가 없습니다."
    )


@pytest.mark.unit
def test_catalog_skill_contains_writable_false_priority_note():
    """catalog-update SKILL.md 예외 절 근처에 writable=false 차단이 플래그보다 우선한다는 교차 참조가 있다."""
    content = _read(_CATALOG_SKILL)
    assert "writable=false" in content, (
        f"{_CATALOG_SKILL} 에 writable=false 우선순위 교차 참조가 없습니다."
    )


@pytest.mark.unit
def test_catalog_skill_contains_update_when_priority_note():
    """catalog-update SKILL.md 예외 절 근처에 update_when 게이트가 플래그보다 우선한다는 교차 참조가 있다."""
    content = _read(_CATALOG_SKILL)
    assert "항상 우선" in content or "우선한다" in content, (
        f"{_CATALOG_SKILL} 에 update_when 우선순위 교차 참조가 없습니다."
    )


# ──────────────────────────────────────────────────────────────
# TC-8~10: catalog-update 예외 절 구조 기반 검증 (Cardinality·경로 범위·off 흐름)
# ──────────────────────────────────────────────────────────────

_EXCEPTION_HEADER = "#### 예외 (플래그=사전 승인)"
# 일반 승인 단계 수: B-2 4단계, B-2 5단계 = 2개 + force 경로(B-5-force §4) = 1개 → 최소 3개
_MIN_EXCEPTION_COUNT = 3


@pytest.mark.unit
def test_catalog_skill_exception_clause_cardinality():
    """catalog-update SKILL.md 예외 절 헤더 출현 횟수 ≥ 일반 승인 단계 수(2) + force(1) = 3."""
    content = _read(_CATALOG_SKILL)
    count = content.count(_EXCEPTION_HEADER)
    assert count >= _MIN_EXCEPTION_COUNT, (
        f"{_CATALOG_SKILL} 에 예외 절 헤더('{_EXCEPTION_HEADER}')가 {count}개 존재 — "
        f"최소 {_MIN_EXCEPTION_COUNT}개 필요합니다. "
        f"(B-2 4단계, B-2 5단계, B-5-force §4 각 1개)"
    )


@pytest.mark.unit
def test_catalog_skill_exception_clause_exists_outside_force():
    """catalog-update SKILL.md 일반 승인 경로(force 외)에도 예외 절이 존재한다.

    B-5-force 섹션 바깥에서 예외 절 헤더가 최소 1회 등장해야 한다.
    """
    content = _read(_CATALOG_SKILL)
    # B-5-force 섹션 이전 텍스트에서 예외 절 헤더를 찾는다
    force_section_marker = "# B-5-force."
    force_idx = content.find(force_section_marker)
    assert force_idx != -1, (
        f"{_CATALOG_SKILL} 에 'B-5-force' 섹션이 없습니다."
    )
    pre_force_content = content[:force_idx]
    assert _EXCEPTION_HEADER in pre_force_content, (
        f"{_CATALOG_SKILL} 에서 B-5-force 섹션 이전(일반 승인 경로)에 "
        f"예외 절 헤더('{_EXCEPTION_HEADER}')가 없습니다."
    )


@pytest.mark.unit
def test_catalog_skill_exception_clause_off_fallback_phrase():
    """catalog-update SKILL.md 일반 경로 예외 절이 off일 때 '종전 승인 흐름' 문구를 포함한다(무조건 무인 아님)."""
    content = _read(_CATALOG_SKILL)
    # B-5-force 이전의 일반 경로 예외 절에 "종전 승인 흐름" 문구가 있어야 한다
    force_section_marker = "# B-5-force."
    force_idx = content.find(force_section_marker)
    assert force_idx != -1, (
        f"{_CATALOG_SKILL} 에 'B-5-force' 섹션이 없습니다."
    )
    pre_force_content = content[:force_idx]
    assert "종전 승인 흐름" in pre_force_content, (
        f"{_CATALOG_SKILL} 일반 경로 예외 절에 "
        f"'종전 승인 흐름' 문구가 없습니다 — off일 때 무조건 무인 진행이 되어서는 안 됩니다."
    )

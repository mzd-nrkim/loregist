"""
test_drift.py — drift.compute_drift_paths() 단위 테스트

모두 @pytest.mark.unit, tmp_path 픽스처로 격리.
실제 프로젝트 파일·DB·모델에 의존하지 않는다.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from loregist.drift import compute_drift_paths, drift_summary


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _write_last_update(catalog_dir: Path, ts: datetime) -> None:
    """catalog_dir/.last_catalog_update 에 ISO 타임스탬프를 기록한다."""
    (catalog_dir / ".last_catalog_update").write_text(ts.isoformat(), encoding="utf-8")


def _make_handbook(path: Path, content: str = "# doc") -> Path:
    """handbook 파일을 생성하고 경로를 반환한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _set_mtime(path: Path, ts: datetime) -> None:
    """path의 mtime을 ts로 설정한다."""
    epoch = ts.timestamp()
    os.utime(path, (epoch, epoch))


# ──────────────────────────────────────────────────────────────
# 테스트
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_drift_new_handbook_after_last_update(tmp_path: Path) -> None:
    """.last_catalog_update 이후 생성된 파일 → drift에 포함."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    ref_time = datetime(2024, 1, 10, 12, 0, 0)
    _write_last_update(catalog_dir, ref_time)

    # ref_time + 1시간 뒤 mtime
    new_file = _make_handbook(tmp_path / "new.md")
    _set_mtime(new_file, ref_time + timedelta(hours=1))

    result = compute_drift_paths([new_file], catalog_dir)
    assert result == [new_file]


@pytest.mark.unit
def test_drift_modified_handbook_after_last_update(tmp_path: Path) -> None:
    """.last_catalog_update 이후 mtime 갱신된 파일 → drift에 포함."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    ref_time = datetime(2024, 3, 5, 9, 0, 0)
    _write_last_update(catalog_dir, ref_time)

    hb = _make_handbook(tmp_path / "existing.md")
    # .last_catalog_update 보다 30분 뒤로 mtime 설정
    _set_mtime(hb, ref_time + timedelta(minutes=30))

    result = compute_drift_paths([hb], catalog_dir)
    assert result == [hb]


@pytest.mark.unit
def test_drift_all_reflected_empty_result(tmp_path: Path) -> None:
    """모든 handbook이 .last_catalog_update 이전 → 빈 리스트."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    ref_time = datetime(2024, 6, 1, 12, 0, 0)
    _write_last_update(catalog_dir, ref_time)

    hb = _make_handbook(tmp_path / "old.md")
    _set_mtime(hb, ref_time - timedelta(days=1))

    result = compute_drift_paths([hb], catalog_dir)
    assert result == []


@pytest.mark.unit
def test_drift_empty_handbook_list(tmp_path: Path) -> None:
    """handbook 0개 → 빈 리스트, 에러 없음."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    _write_last_update(catalog_dir, datetime(2024, 1, 1))

    result = compute_drift_paths([], catalog_dir)
    assert result == []


@pytest.mark.unit
def test_drift_boundary_zero_drift(tmp_path: Path) -> None:
    """미반영 0건 → 빈 결과, 에러 없음."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    ref_time = datetime(2024, 9, 15, 0, 0, 0)
    _write_last_update(catalog_dir, ref_time)

    files = []
    for i in range(3):
        hb = _make_handbook(tmp_path / f"doc{i}.md")
        _set_mtime(hb, ref_time - timedelta(days=i + 1))
        files.append(hb)

    result = compute_drift_paths(files, catalog_dir)
    assert result == []


@pytest.mark.unit
def test_drift_cross_check_manual_vs_function(tmp_path: Path) -> None:
    """직접 mtime ↔ .last_catalog_update 수동 비교 결과와 compute_drift_paths 결과 일치."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    ref_time = datetime(2024, 5, 20, 10, 0, 0)
    _write_last_update(catalog_dir, ref_time)

    files = []
    expected_drift = []
    for i, delta_hours in enumerate([-2, 1, -1, 3, 0]):
        hb = _make_handbook(tmp_path / f"f{i}.md")
        mtime = ref_time + timedelta(hours=delta_hours)
        _set_mtime(hb, mtime)
        files.append(hb)
        if delta_hours > 0:
            expected_drift.append(hb)

    result = compute_drift_paths(files, catalog_dir)
    assert sorted(result) == sorted(expected_drift)


@pytest.mark.unit
def test_drift_no_last_update_no_index_all_drift(tmp_path: Path) -> None:
    """.last_catalog_update 부재 + TOPICS/DECISIONS도 없음 → 존재하는 파일 전부 drift."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()  # 빈 디렉터리, .last_catalog_update 없음

    files = [
        _make_handbook(tmp_path / "a.md"),
        _make_handbook(tmp_path / "b.md"),
    ]

    result = compute_drift_paths(files, catalog_dir)
    assert sorted(result) == sorted(files)


@pytest.mark.unit
def test_drift_catalog_dir_none_returns_empty(tmp_path: Path) -> None:
    """catalog_dir=None → 빈 리스트 반환(catalog 비대상 프로젝트)."""
    files = [_make_handbook(tmp_path / "x.md")]
    result = compute_drift_paths(files, None)
    assert result == []


@pytest.mark.unit
def test_drift_nonexistent_handbook_paths_skipped(tmp_path: Path) -> None:
    """존재하지 않는 handbook 경로는 건너뜀 — 에러 없이."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    _write_last_update(catalog_dir, datetime(2024, 1, 1))

    ghost = tmp_path / "does_not_exist.md"  # 생성 안 함

    result = compute_drift_paths([ghost], catalog_dir)
    assert result == []


@pytest.mark.unit
def test_drift_cardinality_zero(tmp_path: Path) -> None:
    """미반영 0건 — 개수 정확."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    ref_time = datetime(2024, 2, 1)
    _write_last_update(catalog_dir, ref_time)

    hb = _make_handbook(tmp_path / "doc.md")
    _set_mtime(hb, ref_time - timedelta(days=1))

    result = compute_drift_paths([hb], catalog_dir)
    assert len(result) == 0


@pytest.mark.unit
def test_drift_cardinality_one(tmp_path: Path) -> None:
    """미반영 1건 — 개수 정확."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    ref_time = datetime(2024, 2, 1)
    _write_last_update(catalog_dir, ref_time)

    old = _make_handbook(tmp_path / "old.md")
    _set_mtime(old, ref_time - timedelta(days=1))

    new = _make_handbook(tmp_path / "new.md")
    _set_mtime(new, ref_time + timedelta(hours=2))

    result = compute_drift_paths([old, new], catalog_dir)
    assert len(result) == 1
    assert result[0] == new


@pytest.mark.unit
def test_drift_cardinality_multiple(tmp_path: Path) -> None:
    """미반영 N건 — 정확한 개수 반환."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    ref_time = datetime(2024, 3, 1)
    _write_last_update(catalog_dir, ref_time)

    n_drift = 4
    drift_files = []
    for i in range(n_drift):
        hb = _make_handbook(tmp_path / f"new_{i}.md")
        _set_mtime(hb, ref_time + timedelta(hours=i + 1))
        drift_files.append(hb)

    for i in range(2):
        hb = _make_handbook(tmp_path / f"old_{i}.md")
        _set_mtime(hb, ref_time - timedelta(days=i + 1))

    all_files = drift_files + [tmp_path / f"old_{i}.md" for i in range(2)]
    result = compute_drift_paths(all_files, catalog_dir)
    assert len(result) == n_drift


@pytest.mark.unit
def test_drift_fallback_to_index_mtime(tmp_path: Path) -> None:
    """.last_catalog_update 없고 TOPICS.md만 있을 때 mtime을 reference로 사용."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    topics_md = catalog_dir / "TOPICS.md"
    topics_md.write_text("# TOPICS", encoding="utf-8")
    ref_time = datetime(2024, 7, 1, 6, 0, 0)
    _set_mtime(topics_md, ref_time)

    old = _make_handbook(tmp_path / "old.md")
    _set_mtime(old, ref_time - timedelta(hours=2))

    new = _make_handbook(tmp_path / "new.md")
    _set_mtime(new, ref_time + timedelta(hours=1))

    result = compute_drift_paths([old, new], catalog_dir)
    assert result == [new]


@pytest.mark.unit
def test_drift_fallback_uses_max_of_both_index_files(tmp_path: Path) -> None:
    """TOPICS.md / DECISIONS.md 둘 다 있을 때 mtime 최댓값을 reference로 사용."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()

    topics_md = catalog_dir / "TOPICS.md"
    topics_md.write_text("# T", encoding="utf-8")
    decisions_md = catalog_dir / "DECISIONS.md"
    decisions_md.write_text("# D", encoding="utf-8")

    earlier = datetime(2024, 8, 1, 0, 0, 0)
    later = datetime(2024, 8, 2, 0, 0, 0)
    _set_mtime(topics_md, earlier)
    _set_mtime(decisions_md, later)  # DECISIONS가 더 최신

    # later(DECISIONS mtime)보다 1시간 뒤여야 drift
    hb_drift = _make_handbook(tmp_path / "drift.md")
    _set_mtime(hb_drift, later + timedelta(hours=1))

    # later와 earlier 사이 → drift 아님
    hb_between = _make_handbook(tmp_path / "between.md")
    _set_mtime(hb_between, earlier + timedelta(hours=1))

    result = compute_drift_paths([hb_drift, hb_between], catalog_dir)
    assert result == [hb_drift]


@pytest.mark.unit
def test_drift_summary_schema(tmp_path: Path, monkeypatch) -> None:
    """drift_summary 결과의 키·타입 검증(project:str, count:int, files:list[str])."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    ref_time = datetime(2024, 4, 1)
    _write_last_update(catalog_dir, ref_time)

    hb = _make_handbook(tmp_path / "readme.md")
    _set_mtime(hb, ref_time + timedelta(hours=1))

    # config.PROJECTS에 임시 프로젝트 주입 (monkeypatch로 범위 내 복원)
    import loregist.config as cfg_mod
    import loregist.drift as drift_mod

    fake_projects = {
        "__test_drift__": {
            "handbook": [{"path": hb, "writable": False, "update_when": None}],
            "catalog": catalog_dir,
        }
    }
    monkeypatch.setattr(cfg_mod, "PROJECTS", fake_projects)
    monkeypatch.setattr(drift_mod, "config", cfg_mod)

    result = drift_summary("__test_drift__")

    assert isinstance(result["project"], str)
    assert isinstance(result["count"], int)
    assert isinstance(result["files"], list)
    assert all(isinstance(f, str) for f in result["files"])
    assert result["project"] == "__test_drift__"
    assert result["count"] == 1
    assert str(hb) in result["files"]


@pytest.mark.unit
def test_drift_result_is_sorted(tmp_path: Path) -> None:
    """결과가 정렬된 list[Path]임을 보장한다."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    ref_time = datetime(2024, 5, 1)
    _write_last_update(catalog_dir, ref_time)

    files = []
    for name in ("c.md", "a.md", "b.md"):
        hb = _make_handbook(tmp_path / name)
        _set_mtime(hb, ref_time + timedelta(hours=1))
        files.append(hb)

    result = compute_drift_paths(files, catalog_dir)
    assert result == sorted(result)


@pytest.mark.unit
def test_drift_all_tmp_path(tmp_path: Path) -> None:
    """모든 경로가 tmp_path 내부임을 보장 — 실 프로젝트 파일 비의존 확인."""
    catalog_dir = tmp_path / "_wiki"
    catalog_dir.mkdir()
    ref_time = datetime(2024, 6, 1)
    _write_last_update(catalog_dir, ref_time)

    hb = _make_handbook(tmp_path / "doc.md")
    _set_mtime(hb, ref_time + timedelta(minutes=10))

    result = compute_drift_paths([hb], catalog_dir)
    for p in result:
        assert str(p).startswith(str(tmp_path)), (
            f"결과 경로 {p}가 tmp_path {tmp_path} 외부임 — 실 프로젝트 비의존 위반"
        )

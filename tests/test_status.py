"""
tests/test_status.py
catalog 경고 빈 줄 회귀 테스트 — DB 없이 단위 실행 가능 (가짜 conn + monkeypatch PROJECTS)
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_fake_conn(rows=None):
    """run_status 내부의 conn.cursor() 호출을 stub하는 가짜 conn을 반환한다.

    rows: cursor.fetchall()이 반환할 시퀀스. 기본값은 빈 리스트(임베딩 없음).
    """
    if rows is None:
        rows = []
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ──────────────────────────────────────────────────────────────
# 경고 0건 — catalog 경고 뒤 빈 줄 미출력
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_catalog_warn_zero_no_trailing_blank_line(monkeypatch, capsys):
    """catalog 경고 0건(catalog=None)일 때 catalog 경고 블록 뒤 빈 줄이 출력되지 않는다."""
    from loregist import status

    # 모든 프로젝트의 catalog가 None → 경고 0건
    fake_projects = {
        "proj-a": {"catalog": None, "vault": "/some/vault"},
        "proj-b": {"catalog": None, "vault": "/other/vault"},
    }
    monkeypatch.setattr("loregist.status.PROJECTS", fake_projects)

    conn = _make_fake_conn(rows=[])
    status.run_status(conn)

    captured = capsys.readouterr()
    # catalog 경고 블록 뒤 빈 줄(\n\n)이 연속으로 나타나지 않아야 한다.
    # run_status는 청크 섹션 뒤에 빈 줄 1개를 출력하므로 "\n\n"은 최소 1회 있을 수 있다.
    # catalog 경고가 없으면 경고 뒤 추가 빈 줄이 없으므로 "\n\n\n" 패턴이 없어야 한다.
    assert "\n\n\n" not in captured.out, (
        "경고 0건인데 catalog 경고 블록 뒤 빈 줄이 출력됨: "
        + repr(captured.out)
    )


@pytest.mark.unit
def test_catalog_warn_zero_projects_empty_no_blank(monkeypatch, capsys):
    """PROJECTS가 비어 있어도(프로젝트 0개) 경고 0건으로 처리되어 빈 줄 미출력, 예외 없음 (Cardinality/Error)."""
    from loregist import status

    monkeypatch.setattr("loregist.status.PROJECTS", {})

    conn = _make_fake_conn(rows=[])
    status.run_status(conn)  # 예외 없이 종료해야 함

    captured = capsys.readouterr()
    assert "\n\n\n" not in captured.out, (
        "PROJECTS 0개인데 catalog 경고 빈 줄이 출력됨: " + repr(captured.out)
    )


@pytest.mark.unit
def test_catalog_warn_single_project_catalog_none_no_blank(monkeypatch, capsys):
    """프로젝트 1개, catalog=None → 경고 0건, 빈 줄 미출력 (Cardinality/Boundary)."""
    from loregist import status

    fake_projects = {
        "only-proj": {"catalog": None},
    }
    monkeypatch.setattr("loregist.status.PROJECTS", fake_projects)

    conn = _make_fake_conn(rows=[])
    status.run_status(conn)

    captured = capsys.readouterr()
    assert "\n\n\n" not in captured.out


# ──────────────────────────────────────────────────────────────
# 경고 1건 이상 — catalog 경고 뒤 빈 줄 유지 (회귀 방지)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_catalog_warn_one_keeps_trailing_blank_line(monkeypatch, capsys):
    """catalog 경고 1건(존재하지 않는 _wiki 경로)일 때 경고 뒤 빈 줄 1개가 출력된다 (회귀 방지)."""
    from loregist import status

    nonexistent = Path("/nonexistent/__test_wiki_xyz__")
    fake_projects = {
        "proj-missing-wiki": {"catalog": nonexistent},
    }
    monkeypatch.setattr("loregist.status.PROJECTS", fake_projects)

    conn = _make_fake_conn(rows=[])
    status.run_status(conn)

    captured = capsys.readouterr()
    # 경고 줄이 출력된 뒤 빈 줄(\n\n — 경고 줄 끝 \n + 빈 줄 print() \n)이 있어야 한다.
    assert "\n\n" in captured.out, (
        "경고 1건인데 catalog 경고 뒤 빈 줄이 없음: " + repr(captured.out)
    )
    # 경고 텍스트가 포함되어 있는지도 확인
    assert "_wiki" in captured.out or "catalog-init" in captured.out


@pytest.mark.unit
def test_catalog_warn_multiple_keeps_one_trailing_blank_line(monkeypatch, capsys):
    """catalog 경고 N건(N≥2)일 때 경고 블록 뒤 빈 줄이 정확히 1개 (Cardinality/Boundary)."""
    from loregist import status

    nonexistent_a = Path("/nonexistent/__test_wiki_a__")
    nonexistent_b = Path("/nonexistent/__test_wiki_b__")
    fake_projects = {
        "proj-a": {"catalog": nonexistent_a},
        "proj-b": {"catalog": nonexistent_b},
    }
    monkeypatch.setattr("loregist.status.PROJECTS", fake_projects)

    conn = _make_fake_conn(rows=[])
    status.run_status(conn)

    captured = capsys.readouterr()
    # 마지막 경고 줄 이후 빈 줄이 있어야 하므로 출력 끝 쪽에 \n\n 존재
    assert "\n\n" in captured.out


# ──────────────────────────────────────────────────────────────
# 경고 0건 vs 1건: 빈 줄 수 차이 교차 확인 (Cross-check)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_catalog_warn_blank_line_count_diff(monkeypatch, capsys):
    """경고 0건일 때 빈 줄이 경고 1건일 때보다 1개 적다 (Cross-check)."""
    from loregist import status

    # 경고 0건 실행
    monkeypatch.setattr("loregist.status.PROJECTS", {"p": {"catalog": None}})
    conn = _make_fake_conn(rows=[])
    status.run_status(conn)
    out_zero = capsys.readouterr().out
    blank_count_zero = out_zero.count("\n\n")

    # 경고 1건 실행
    nonexistent = Path("/nonexistent/__test_wiki_cross__")
    monkeypatch.setattr("loregist.status.PROJECTS", {"p": {"catalog": nonexistent}})
    conn2 = _make_fake_conn(rows=[])
    status.run_status(conn2)
    out_one = capsys.readouterr().out
    blank_count_one = out_one.count("\n\n")

    assert blank_count_one > blank_count_zero, (
        f"경고 1건({blank_count_one}개 \\n\\n)이 "
        f"경고 0건({blank_count_zero}개 \\n\\n)보다 많아야 함"
    )


# ──────────────────────────────────────────────────────────────
# project_filter 적용 시 필터링된 프로젝트만 경고 대상 (Conformance)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_catalog_warn_project_filter_zero_warn_no_blank(monkeypatch, capsys):
    """project_filter를 적용했을 때 대상 프로젝트에 경고가 없으면 빈 줄 미출력 (Conformance)."""
    from loregist import status

    nonexistent = Path("/nonexistent/__test_wiki_filter__")
    fake_projects = {
        "proj-ok": {"catalog": None},        # 필터 대상 — 경고 없음
        "proj-bad": {"catalog": nonexistent}, # 필터 제외 — 경고 있어도 무시
    }
    monkeypatch.setattr("loregist.status.PROJECTS", fake_projects)

    conn = _make_fake_conn(rows=[])
    status.run_status(conn, project_filter="proj-ok")

    captured = capsys.readouterr()
    assert "\n\n\n" not in captured.out, (
        "필터 후 경고 0건인데 빈 줄이 출력됨: " + repr(captured.out)
    )

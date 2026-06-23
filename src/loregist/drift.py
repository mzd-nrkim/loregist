"""
drift.py — catalog 미반영 handbook 파일(drift) 식별 헬퍼

계층 구조:
  compute_drift_paths()  순수 함수 (config 비의존, 단위테스트 직접 호출)
  compute_drift()        config.PROJECTS 래퍼
  drift_summary()        JSON 직렬화용 요약 dict 반환

code→doc 방향 안전망 (Phase B, 방식 b):
  FORCE_CHECK_INTERVAL_DAYS  전수 점검 최대 허용 간격 (기본 7일)
  compute_drift_paths의 force_check_stamp 파라미터로 활성화.
  마지막 --force 전수점검 시점 스탬프 파일을 읽어, 기간 초과 시
  reference=None(전체 drift)으로 폴백하여 전수 점검을 유도한다.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loregist import config

# code→doc 방향 안전망: 전수 점검 최대 허용 간격
FORCE_CHECK_INTERVAL_DAYS: int = 7


def compute_drift_paths(
    handbook_paths: list[Path],
    catalog_dir: "Path | None",
    *,
    force_check_stamp: Optional[Path] = None,
) -> list[Path]:
    """
    catalog에 아직 반영되지 않은 handbook 파일(drift) 목록을 반환한다.

    Parameters
    ----------
    handbook_paths:
        확인할 handbook 파일 경로 목록.  존재하지 않는 경로는 무시한다.
    catalog_dir:
        catalog 디렉터리 경로.  None이면 빈 리스트 반환(catalog 비대상 프로젝트).
    force_check_stamp:
        (Phase B 안전망) "마지막 --force 전수점검 시점"을 기록한 스탬프 파일 경로.
        - 파일이 존재하면: mtime을 읽어 FORCE_CHECK_INTERVAL_DAYS(7일) 이상 경과 시
          reference=None으로 강제 폴백 → 존재하는 모든 handbook 파일이 drift로 표면화.
        - 파일이 없거나 None이면: 안전망 비활성(기존 동작 유지).
        이 파라미터는 code→doc 방향 stale 미감지(코드만 바뀌고 handbook mtime 불변)를
        보완한다. 호출자가 --force 실행 후 이 파일을 갱신하면 7일 주기 전수 점검이 보장된다.

    Returns
    -------
    정렬된 list[Path] — mtime이 reference 이후인(또는 reference=None인) handbook 파일.

    Reference 결정 규칙 (우선순위):
      0. force_check_stamp가 있고 FORCE_CHECK_INTERVAL_DAYS 이상 경과
         → reference=None 강제(전체 drift) — code→doc 방향 안전망
      1. catalog_dir / ".last_catalog_update" (신규) 또는 ".last_update" (구, 하위호환)
         - 40자리 hex SHA → git commit time으로 변환
         - ISO 문자열 → 직접 파싱
      2. TOPICS.md / DECISIONS.md 의 mtime 최댓값
      3. 위 어느 것도 없으면 None → 존재하는 모든 handbook 파일이 drift
    """
    if catalog_dir is None:
        return []

    # 우선순위 0: code→doc 방향 안전망 — force_check_stamp 기간 초과 시 전체 폴백
    if force_check_stamp is not None and force_check_stamp.exists():
        last_force_check = datetime.fromtimestamp(force_check_stamp.stat().st_mtime)
        elapsed = datetime.now() - last_force_check
        if elapsed >= timedelta(days=FORCE_CHECK_INTERVAL_DAYS):
            # 전수 점검 기간 초과 → 존재하는 모든 handbook 파일을 drift로 반환
            return sorted(p for p in handbook_paths if p.exists())

    reference: "datetime | None" = None

    # 우선순위 1: .last_catalog_update (신규) 또는 .last_update (구, 하위호환)
    _stamp_file = catalog_dir / ".last_catalog_update"
    _legacy_file = catalog_dir / ".last_update"
    _stamp_path = _stamp_file if _stamp_file.exists() else (_legacy_file if _legacy_file.exists() else None)
    if _stamp_path is not None:
        _stamp = _stamp_path.read_text(encoding="utf-8").strip()
        _SHA_RE = re.compile(r'^[0-9a-f]{40}$')
        if _SHA_RE.match(_stamp):
            try:
                _ts = subprocess.check_output(
                    ["git", "-C", str(catalog_dir), "show", "-s", "--format=%cI", _stamp],
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
                reference = datetime.fromisoformat(_ts)
            except Exception:
                reference = None  # fallback: drift 전체(아래 None 처리)
        else:
            try:
                reference = datetime.fromisoformat(_stamp)
            except ValueError:
                reference = None  # 깨진 포맷 → fallback

    # 우선순위 2: TOPICS.md / DECISIONS.md mtime
    if reference is None:
        index_mtimes: list[float] = []
        for name in ("TOPICS.md", "DECISIONS.md"):
            p = catalog_dir / name
            if p.exists():
                index_mtimes.append(p.stat().st_mtime)
        if index_mtimes:
            reference = datetime.fromtimestamp(max(index_mtimes))

    # reference=None → 존재하는 모든 handbook 파일이 drift
    result: list[Path] = []
    for p in handbook_paths:
        if not p.exists():
            continue
        if reference is None:
            result.append(p)
        else:
            file_mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if file_mtime > reference:
                result.append(p)

    return sorted(result)


def compute_drift(project_name: str) -> list[Path]:
    """
    config.PROJECTS에서 handbook 경로와 catalog_dir를 꺼내
    compute_drift_paths()에 위임한다.

    Parameters
    ----------
    project_name:
        PROJECTS 딕셔너리 키.

    Returns
    -------
    정렬된 list[Path].
    """
    cfg = config.PROJECTS[project_name]
    handbook_paths = [entry["path"] for entry in cfg.get("handbook", [])]
    catalog_dir: "Path | None" = cfg.get("catalog")
    return compute_drift_paths(handbook_paths, catalog_dir)


def drift_summary(project_name: str) -> dict:
    """
    drift 계산 결과를 JSON 직렬화 가능한 고정 스키마 dict로 반환한다.

    Returns
    -------
    {
        "project": str,       # 프로젝트 키
        "count":   int,       # drift 파일 수
        "files":   list[str]  # 절대경로 문자열 정렬 목록
    }
    """
    drifted = compute_drift(project_name)
    return {
        "project": project_name,
        "count": len(drifted),
        "files": [str(p) for p in drifted],
    }

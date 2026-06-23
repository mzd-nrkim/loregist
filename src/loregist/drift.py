"""
drift.py — catalog 미반영 handbook 파일(drift) 식별 헬퍼

계층 구조:
  compute_drift_paths()  순수 함수 (config 비의존, 단위테스트 직접 호출)
  compute_drift()        config.PROJECTS 래퍼
  drift_summary()        JSON 직렬화용 요약 dict 반환
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

from loregist import config


def compute_drift_paths(
    handbook_paths: list[Path],
    catalog_dir: "Path | None",
) -> list[Path]:
    """
    catalog에 아직 반영되지 않은 handbook 파일(drift) 목록을 반환한다.

    Parameters
    ----------
    handbook_paths:
        확인할 handbook 파일 경로 목록.  존재하지 않는 경로는 무시한다.
    catalog_dir:
        catalog 디렉터리 경로.  None이면 빈 리스트 반환(catalog 비대상 프로젝트).

    Returns
    -------
    정렬된 list[Path] — mtime이 reference 이후인(또는 reference=None인) handbook 파일.

    Reference 결정 규칙 (우선순위):
      1. catalog_dir / ".last_catalog_update" (신규) 또는 ".last_update" (구, 하위호환)
         - 40자리 hex SHA → git commit time으로 변환
         - ISO 문자열 → 직접 파싱
      2. TOPICS.md / DECISIONS.md 의 mtime 최댓값
      3. 위 어느 것도 없으면 None → 존재하는 모든 handbook 파일이 drift
    """
    if catalog_dir is None:
        return []

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

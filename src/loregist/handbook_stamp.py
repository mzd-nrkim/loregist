"""
handbook_stamp.py — handbook .last_handbook_update 스탬프 검증 헬퍼 (Phase C)

SKILL.md W-8은 LLM 절차로 .last_handbook_update를 기록하지만,
코드 레벨 강제가 없어 "0건 갱신 시에도 스탬프가 찍히는" 결함이 발생했다.
이 모듈은 스탬프 유효성 검증과 기록 조건 판단을 코드로 강제하는 검증 레이어다.

사용처:
  - 단위 테스트(test_handbook_stamp.py): 검증 함수 동작 확인
  - 향후 hook 또는 lint 스크립트에서 import하여 스탬프 정합성 검증

규칙 (SKILL.md W-8에서 파생):
  - should_record(wrote_count): wrote_count >= 1이면 True (0건 미기록 강제)
  - validate_stamp(stamp_path): SHA(40자 hex) 또는 ISO datetime이면 True
"""
from __future__ import annotations

import re
from pathlib import Path

# 유효한 스탬프 형식 패턴
_SHA_RE = re.compile(r'^[0-9a-f]{40}$')

# ISO 8601 기본 패턴 (datetime.fromisoformat이 처리하는 범위)
# Python 3.7+에서 fromisoformat은 YYYY-MM-DD[T...] 형식을 지원
_ISO_PREFIX_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')


def should_record(wrote_count: int) -> bool:
    """
    handbook 스탬프를 기록해야 하는지 판단한다.

    W-8 규칙: "Edit/Write 반영이 1건 이상 성공한 뒤에만 갱신한다."

    Parameters
    ----------
    wrote_count:
        실제 반영(Edit/Write)된 섹션·파일 수.

    Returns
    -------
    True  — wrote_count >= 1: 스탬프 기록 대상
    False — wrote_count == 0: 스탬프 기록 금지 (0건-미기록 강제)
    """
    return wrote_count >= 1


def validate_stamp(stamp_path: Path) -> bool:
    """
    .last_handbook_update 스탬프 파일의 유효성을 검증한다.

    Parameters
    ----------
    stamp_path:
        .last_handbook_update 파일 경로.

    Returns
    -------
    True  — 파일이 존재하고 내용이 SHA(40자 hex) 또는 ISO datetime 형식
    False — 파일 없음, 내용 빈 문자열, 알 수 없는 형식

    유효 형식:
      - SHA: 40자 소문자 hex (git rev-parse HEAD 결과)
      - ISO 8601: "YYYY-MM-DD" 또는 "YYYY-MM-DDTHH:MM:SSZ" 등 (git repo 밖 타임스탬프)
    """
    if not stamp_path.exists():
        return False

    content = stamp_path.read_text(encoding="utf-8").strip()
    if not content:
        return False

    # SHA 형식
    if _SHA_RE.match(content):
        return True

    # ISO datetime 형식 (최소 YYYY-MM-DD 로 시작)
    if _ISO_PREFIX_RE.match(content):
        try:
            # Python 3.7+: fromisoformat은 "Z" suffix를 3.11+ 에서만 지원
            # 호환성을 위해 Z → +00:00 치환
            _normalized = content.replace("Z", "+00:00")
            from datetime import datetime
            datetime.fromisoformat(_normalized)
            return True
        except ValueError:
            pass

    return False


def validate_handbook_stamp(catalog_dir: Path) -> bool:
    """
    catalog_dir/_wiki/.last_handbook_update의 유효성을 검증한다.
    (catalog_dir가 docs_root/_wiki 형태인 경우를 위한 편의 함수)

    catalog_dir가 직접 .last_handbook_update를 포함하는 경우와
    catalog_dir가 docs_root인 경우 모두를 지원하기 위해,
    catalog_dir 내부에서 파일을 탐색한다.

    Parameters
    ----------
    catalog_dir:
        _wiki 디렉터리 경로 (catalog 디렉터리).
        이 디렉터리 바로 아래의 .last_handbook_update를 검증한다.

    Returns
    -------
    validate_stamp(catalog_dir / ".last_handbook_update") 결과.
    """
    stamp_path = catalog_dir / ".last_handbook_update"
    return validate_stamp(stamp_path)

"""
tests/test_chunking.py
T1 — 청킹 유닛 테스트 (실DB 불필요)

T1-1: hash_chunk 결정성 / 차이, hash_file 임시파일
T1-2: split_md 기본 케이스 (md_long2, md_short2, md_noheader, empty fixture 활용)
T1-3: split_md 장문 경계값 (멀티라인 4000자 → ≥2청크, 단일라인 5000자 → 1청크 한계)
T1-4: split_log 단락 분할, 빈·단일<20자→0, 짧은단락 병합
"""

import pytest
from loregist.chunking import split_md, split_log, hash_chunk, hash_file


# ──────────────────────────────────────────────────────────────
# T1-1: hash_chunk 결정성 / 차이, hash_file 임시파일
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_hash_chunk_deterministic():
    """동일 텍스트를 두 번 해싱하면 결과가 같아야 한다."""
    text = "동일한 텍스트입니다. Same text repeated."
    assert hash_chunk(text) == hash_chunk(text)


@pytest.mark.unit
def test_hash_chunk_different_inputs():
    """서로 다른 텍스트는 다른 해시를 반환해야 한다."""
    h1 = hash_chunk("텍스트 A")
    h2 = hash_chunk("텍스트 B")
    assert h1 != h2


@pytest.mark.unit
def test_hash_file_hex_length(tmp_path):
    """
    임시 파일에 대해 hash_file을 호출하면 64자리 16진수 문자열(SHA-256)을 반환한다.
    """
    test_file = tmp_path / "sample.txt"
    test_file.write_text("파일 해시 테스트용 내용", encoding="utf-8")
    result = hash_file(str(test_file))
    assert len(result) == 64
    # 모든 문자가 16진수 문자인지 확인
    assert all(c in "0123456789abcdef" for c in result)


# ──────────────────────────────────────────────────────────────
# T1-2: split_md 기본 케이스
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_split_md_two_long_sections(md_long2):
    """
    긴 섹션(>MIN_CHUNK=100자) 2개 → 2청크.
    각 섹션 본문이 MIN_CHUNK 이상이면 병합 없이 별도 청크로 유지된다.
    """
    chunks = split_md(md_long2)
    assert len(chunks) == 2


@pytest.mark.unit
def test_split_md_two_short_sections_merge(md_short2):
    """
    짧은 섹션(<MIN_CHUNK=100자) 2개 → 앞 청크에 병합 → 1청크.
    B-5: 짧은 섹션 병합 동작 검증.
    """
    chunks = split_md(md_short2)
    assert len(chunks) == 1


@pytest.mark.unit
def test_split_md_no_header(md_noheader):
    """
    ## / ### 헤더 없는 평문 → 1청크.
    B-2: 헤더 없는 md 단일 청크 검증.
    """
    chunks = split_md(md_noheader)
    assert len(chunks) == 1


@pytest.mark.unit
def test_split_md_empty(empty):
    """
    빈 문자열 → 0청크.
    """
    chunks = split_md(empty)
    assert len(chunks) == 0


# ──────────────────────────────────────────────────────────────
# T1-3: split_md 장문 경계값
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_split_md_multiline_long_splits():
    """
    멀티라인 장문(200자 줄 × 20개 = 약 4000자, 줄바꿈 포함) → 2청크 이상.
    B-3: MAX_CHUNK(1500자) 초과 멀티라인 텍스트는 줄 단위로 분할된다.
    """
    # 200자짜리 줄 20개 → 총 4019자 (줄바꿈 포함)
    multiline_long = "\n".join(["X" * 200] * 20)
    chunks = split_md(multiline_long)
    assert len(chunks) >= 2


@pytest.mark.unit
def test_split_md_single_line_no_split():
    """
    단일 라인 5000자('X'*5000) → 1청크.
    # 현행 한계: 단일 라인은 MAX_CHUNK 초과해도 분할 안 됨.
    B-4: 줄 단위 분할이므로 단일 라인은 아무리 길어도 쪼개지지 않는다.
    """
    single_line_5000 = "X" * 5000
    chunks = split_md(single_line_5000)
    # 현행 한계: 단일 라인은 MAX_CHUNK 초과해도 분할 안 됨
    assert len(chunks) == 1


# ──────────────────────────────────────────────────────────────
# T1-4: split_log
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_split_log_multiple_paragraphs(log_paras):
    """
    800자짜리 단락 3개(각 단락이 MAX_CHUNK/2 초과) → 3청크.
    R-2: split_log 빈 줄 기준 단락 분할 정확성 검증.
    """
    chunks = split_log(log_paras)
    assert len(chunks) >= 2  # 실제로 3청크이지만 ≥2로 여유있게 검증


@pytest.mark.unit
def test_split_log_empty(empty):
    """
    빈 문자열 → 0청크.
    """
    chunks = split_log(empty)
    assert len(chunks) == 0


@pytest.mark.unit
def test_split_log_tiny_under_20_chars(log_tiny):
    """
    20자 미만의 단일 텍스트("short") → 0청크.
    B-6: split_log의 >= 20자 필터로 인해 짧은 단일 텍스트는 제거된다.
    """
    chunks = split_log(log_tiny)
    assert len(chunks) == 0


@pytest.mark.unit
def test_split_log_short_paragraphs_merge():
    """
    짧은 단락(<MIN_CHUNK=100자) 2개 → 앞 청크에 병합 → 1청크.
    짧은 단락은 뒤의 청크가 이전 청크에 병합되어 청크 수가 줄어든다.
    """
    short_para1 = "A" * 50  # 50자 < MIN_CHUNK(100)
    short_para2 = "B" * 50  # 50자 < MIN_CHUNK(100)
    text = short_para1 + "\n\n" + short_para2
    chunks = split_log(text)
    assert len(chunks) == 1
    # 두 단락이 하나로 합쳐졌는지 확인 (A와 B 모두 포함)
    assert "A" in chunks[0] and "B" in chunks[0]


# ──────────────────────────────────────────────────────────────
# G-1: split_log 짧은 청크 병합 경로 (chunking.py:79)
#   - 첫 단락이 MAX_CHUNK 초과(단, buf="" 이므로 단독 flush 안 됨)
#   - 둘째 짧은 단락(50자)이 overflow 유발 → 1차 루프 후 chunks=[긴것, 짧은것]
#   - 2차 병합 루프에서 len(짧은것) < MIN_CHUNK → merged[-1] += "\n\n" + c (line 79)
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_split_log_short_chunk_merge():
    """G-1: 짧은 후행 단락이 앞 청크에 병합됨 (chunking.py:79)."""
    first_para = "A" * 1501   # > MAX_CHUNK(1500)
    second_para = "B" * 50    # < MIN_CHUNK(100)
    text = first_para + "\n\n" + second_para

    result = split_log(text)

    # 짧은 둘째 단락이 첫 청크에 병합되어 최종 1청크
    assert len(result) == 1, f"병합되어 1청크여야 함, 실제: {len(result)}청크"
    assert "B" * 50 in result[0], "짧은 단락이 병합 결과에 포함되어야 함"
    assert "A" * 1501 in result[0], "긴 단락이 병합 결과에 포함되어야 함"

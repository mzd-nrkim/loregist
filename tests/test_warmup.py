"""
tests/test_warmup.py

warmup.main() / warmup.run_warmup() 단위 테스트.
- load_embedder를 mock해 외부 모델 다운로드 없이 검증.
- stderr에 MODEL_NAME 포함 여부를 capsys로 확인.
"""
import sys
from unittest.mock import patch

import pytest

from loregist.config import MODEL_NAME, MODELS_DIR
import loregist.warmup as warmup_mod


@pytest.mark.unit
def test_warmup_calls_load_embedder_once(capsys):
    """load_embedder가 정확히 1회 호출되는지 확인."""
    with patch.object(warmup_mod, "load_embedder") as mock_load:
        warmup_mod.main()

    mock_load.assert_called_once()


@pytest.mark.unit
def test_warmup_stderr_contains_model_name(capsys):
    """stderr 출력에 MODEL_NAME이 포함되어야 한다."""
    with patch.object(warmup_mod, "load_embedder"):
        warmup_mod.main()

    captured = capsys.readouterr()
    assert MODEL_NAME in captured.err, (
        f"stderr에 MODEL_NAME({MODEL_NAME!r})이 포함되어야 함.\n"
        f"실제 stderr:\n{captured.err}"
    )


@pytest.mark.unit
def test_warmup_stderr_contains_completion_message(capsys):
    """stderr 출력에 완료 메시지('완료')와 캐시 경로가 포함되어야 한다."""
    with patch.object(warmup_mod, "load_embedder"):
        warmup_mod.main()

    captured = capsys.readouterr()
    assert "완료" in captured.err, (
        f"stderr에 '완료' 문자열이 포함되어야 함.\n실제 stderr:\n{captured.err}"
    )
    assert "모델 캐시" in captured.err, (
        f"stderr에 '모델 캐시' 문자열이 포함되어야 함.\n실제 stderr:\n{captured.err}"
    )


@pytest.mark.unit
def test_run_warmup_elapsed_format(capsys):
    """run_warmup()이 고정 elapsed 1.5초를 stderr에 '1.5초' 형식으로 출력하는지 확인."""
    # time.monotonic을 mock해 elapsed 1.5초 고정
    call_count = 0

    def fake_monotonic():
        nonlocal call_count
        call_count += 1
        # 첫 호출(start): 0.0, 두 번째 호출(end): 1.5
        return 0.0 if call_count == 1 else 1.5

    with patch.object(warmup_mod, "load_embedder"):
        with patch("loregist.warmup.time.monotonic", side_effect=fake_monotonic):
            warmup_mod.run_warmup()

    captured = capsys.readouterr()
    assert "1.5초" in captured.err, (
        f"stderr에 '1.5초' 문자열이 포함되어야 함.\n실제 stderr:\n{captured.err}"
    )


@pytest.mark.unit
def test_run_warmup_stderr_contains_models_dir(capsys):
    """run_warmup() stderr에 MODELS_DIR 경로가 포함되어야 한다."""
    with patch.object(warmup_mod, "load_embedder"):
        warmup_mod.run_warmup()

    captured = capsys.readouterr()
    assert str(MODELS_DIR) in captured.err, (
        f"stderr에 MODELS_DIR({str(MODELS_DIR)!r})이 포함되어야 함.\n"
        f"실제 stderr:\n{captured.err}"
    )

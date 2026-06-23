"""
loregist warmup — 임베딩 모델 사전 다운로드·캐시 도구.

첫 embed/watch 전 1회 실행으로 모델을 미리 캐시해
"왜 갑자기 멈췄지?" 경험을 방지한다.
"""
import sys
import time

from loregist.config import MODEL_NAME, MODELS_DIR
from loregist.embed import load_embedder


def run_warmup() -> float:
    print(
        f"임베딩 모델 로드 중 ({MODEL_NAME})...",
        file=sys.stderr,
    )

    start = time.monotonic()
    load_embedder()
    elapsed = time.monotonic() - start

    print(
        f"완료 ({elapsed:.1f}초). 모델 캐시: {MODELS_DIR}",
        file=sys.stderr,
    )

    return elapsed


def main() -> None:
    run_warmup()


if __name__ == "__main__":
    main()

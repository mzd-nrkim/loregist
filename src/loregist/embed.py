#!/usr/bin/env python
import argparse
import datetime
import os
import sys
import time
from pathlib import Path

from loregist.config import PROJECTS, MODELS_DIR, MODEL_NAME, WORKSPACE, DEFAULT_EXTENSIONS, get_db_connection, infer_project
from loregist.chunking import hash_file, hash_chunk, split_md, split_log
from loregist import drift as _drift
from loregist import auto_update

_embedder = None

LOGVAULT_DIR = WORKSPACE / "logvault" / "embed-log"


def load_embedder():
    global _embedder
    if _embedder is None:
        # HF/transformers 콘솔 노이즈 억제 (unauthenticated 경고, "Loading weights" tqdm 바 등).
        # import 전에 설정해야 효과가 있다.
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        import logging
        for name in ("huggingface_hub", "transformers", "sentence_transformers"):
            logging.getLogger(name).setLevel(logging.ERROR)
        import warnings
        warnings.filterwarnings("ignore", module="huggingface_hub")
        os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
        # 기업망 SSL inspection 우회 (huggingface_hub / httpx) — 모델 다운로드 시에만 적용
        if os.environ.get("LOREGIST_NO_SSL_VERIFY", "1") == "1":
            import httpx as _httpx
            _orig_httpx_init = _httpx.Client.__init__
            def _httpx_no_verify(self, *a, **kw):
                kw.setdefault("verify", False)
                _orig_httpx_init(self, *a, **kw)
            _httpx.Client.__init__ = _httpx_no_verify
        from sentence_transformers import SentenceTransformer
        # 캐시가 있으면 local_files_only=True로 HF Hub 네트워크 요청을 완전 차단한다.
        # 기업망 SSL 환경에서 Hub 연결 타임아웃이 반복되어 수십 분이 소요되는 문제 방지.
        # 캐시 없으면 False → 정상 다운로드(loregist warmup 시나리오).
        _model_cache = MODELS_DIR / ("models--" + MODEL_NAME.replace("/", "--"))
        _embedder = SentenceTransformer(
            MODEL_NAME,
            cache_folder=str(MODELS_DIR),
            local_files_only=_model_cache.exists(),
        )
    return _embedder


def embed_documents(texts: list[str]) -> list[list[float]]:
    model = load_embedder()
    prefixed = [f"passage: {t}" for t in texts]
    vecs = model.encode(prefixed, batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vecs]


def discover_embed_files(project: str, include_today: bool = False) -> list[tuple[str, str]]:
    cfg = PROJECTS[project]
    files: list[tuple[str, str]] = []
    today = datetime.date.today().strftime("%Y-%m-%d")
    extensions = cfg.get("extensions", DEFAULT_EXTENSIONS[:])

    def _kind(p: Path) -> str:
        # 수집(extensions)과 처리(kind/청킹)는 별개 정책: .md→md/split_md, 그 외→log/split_log(의도된 설계)
        return "md" if p.suffix == ".md" else "log"

    # vault
    vault: Path | None = cfg["vault"]
    if vault and vault.exists():
        collected: list[Path] = []
        for ext in extensions:
            collected.extend(vault.rglob(f"*.{ext}"))
        for p in sorted(set(collected)):
            files.append((str(p), _kind(p)))

    # done/cold (done=rotate 대기 완료문서, cold=cold storage 종착지)
    for key in ("done", "cold"):
        path: Path | None = cfg.get(key)
        if path and path.exists():
            collected = []
            for ext in extensions:
                collected.extend(path.rglob(f"*.{ext}"))
            for p in sorted(set(collected)):
                files.append((str(p), _kind(p)))

    # docs_root (날짜 폴더 안·_wiki 하위 포함, 오늘 폴더 기본 제외)
    docs_root: Path | None = cfg["docs_root"]
    if docs_root and docs_root.exists():
        collected = []
        for ext in extensions:
            collected.extend(docs_root.rglob(f"*.{ext}"))
        for p in sorted(set(collected)):
            rel = p.relative_to(docs_root)
            parts = rel.parts
            if len(parts) >= 2:
                if parts[0] == "_wiki":
                    files.append((str(p), "catalog"))
                elif include_today or parts[0] != today:
                    files.append((str(p), _kind(p)))

    # handbook (분산 파일 목록 — _parse_handbook_sources가 이미 개별 파일로 확장)
    handbook_sources: list = cfg.get("handbook", [])
    if handbook_sources:
        existing_paths = {p for p, _ in files}  # 기존 수집 경로 set (vault/done/cold/docs_root 결과)
        for entry in handbook_sources:
            p: Path = entry["path"]
            if not p.exists():  # B-1-2: 존재하지 않는 경로 스킵
                continue
            path_str = str(p)
            if path_str not in existing_paths:  # B-1-3: 중복 제거 (기존 스캔 우선)
                files.append((path_str, "handbook"))  # B-1-4
                existing_paths.add(path_str)

    return files


def upsert_original(conn, project: str, path: str, kind: str, text: str, file_hash: str) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO doc_originals (project, source_path, source_kind, full_text, file_hash)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (project, source_path)
        DO UPDATE SET full_text = EXCLUDED.full_text,
                      file_hash = EXCLUDED.file_hash,
                      created_at = now()
        RETURNING id
        """,
        (project, path, kind, text, file_hash),
    )
    return cur.fetchone()[0]


def insert_chunks(conn, original_id: int, project: str, path: str, kind: str, chunks: list[str], embeddings: list[list[float]]):
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM doc_chunks WHERE project = %s AND source_path = %s",
        (project, path),
    )
    for chunk_index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        c_hash = hash_chunk(chunk_text)
        cur.execute(
            """
            INSERT INTO doc_chunks (original_id, project, source_path, source_kind, chunk_hash, chunk_text, embedding, chunk_index)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (original_id, project, path, kind, c_hash, chunk_text, embedding, chunk_index),
        )


def load_existing_hashes(conn, project: str) -> dict[str, str]:
    """DB에서 project의 기존 file_hash를 {source_path: file_hash} 로 반환."""
    cur = conn.cursor()
    cur.execute(
        "SELECT source_path, file_hash FROM doc_originals WHERE project = %s",
        (project,),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def write_embed_log(
    *,
    incremental: bool,
    processed: int,
    skipped: int,
    errors: int,
    elapsed: float,
):
    """logvault/embed-log/YYYY-MM-DD.log 에 실행 결과를 append."""
    LOGVAULT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGVAULT_DIR / f"{datetime.date.today()}.log"

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode = "incremental" if incremental else "full"
    status = "FAIL" if errors > 0 else "OK"
    line = (
        f"[{now}] mode={mode} processed={processed} skipped={skipped} "
        f"errors={errors} elapsed={elapsed:.1f}s status={status}\n"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def embed_file(conn, project: str, path: str) -> None:
    """단일 파일을 임베딩하여 DB에 upsert한다.

    watch.py 등 외부에서 직접 호출 가능한 공개 함수.
    conn: psycopg2 connection (호출자가 관리)
    project: 프로젝트 키
    path: 임베딩할 파일 절대경로
    """
    p = Path(path)
    # kind 결정: _catalog > handbook > 확장자 기준
    cfg = PROJECTS[project]
    docs_root: Path | None = cfg.get("docs_root")
    handbook_paths = {str(entry["path"]) for entry in cfg.get("handbook", [])}
    if docs_root and p.is_relative_to(docs_root) and p.relative_to(docs_root).parts[0] == "_wiki":
        kind = "catalog"
    elif str(p) in handbook_paths:
        kind = "handbook"
    else:
        kind = "md" if p.suffix == ".md" else "log"

    fhash = hash_file(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    original_id = upsert_original(conn, project, path, kind, text, fhash)

    chunks = split_md(text) if p.suffix == ".md" else split_log(text)
    if chunks:
        embeddings = embed_documents(chunks)
        insert_chunks(conn, original_id, project, path, kind, chunks, embeddings)

    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="문서/로그 임베딩 파이프라인")
    parser.add_argument("--project", help="프로젝트명 (기본: cwd 추론)")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 파일 목록만 출력")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="변경된 파일(file_hash 불일치)만 임베딩. 미변경 파일은 스킵.",
    )
    parser.add_argument(
        "--include-today",
        action="store_true",
        help="오늘 날짜 폴더(docs_root/YYYY-MM-DD/)를 임베딩 대상에 포함. 기본은 제외.",
    )
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        metavar="PATH",
        help="단건 임베딩 대상 파일 경로(반복 가능). 지정 시 전체 스캔 대신 해당 파일만 임베딩.",
    )
    args = parser.parse_args()

    project = infer_project(explicit=args.project)
    if project not in PROJECTS:
        print(f"오류: 미등록 프로젝트 '{project}'. projects.toml에 추가하세요.", file=sys.stderr)
        sys.exit(1)
    print(f"프로젝트: {project}")

    # --file 분기: 지정 파일만 임베딩하고 early-return (drift 계산 블록 도달 차단 — 재귀 1차 수단)
    # getattr 안전 접근: 수동 Namespace로 main()을 호출하는 기존 테스트 호환(argparse 경유 시 default=None)
    if getattr(args, "files", None):
        # 단건 호출은 빈도가 낮으므로 hash 비교 없이 항상 upsert (단순·안전)
        with get_db_connection() as conn:
            for path in args.files:
                embed_file(conn, project, path)
                print(f"임베딩 완료: {path}")
        return

    files = discover_embed_files(project, include_today=args.include_today)
    print(f"대상 파일: {len(files)}개")

    if args.dry_run:
        for path, kind in files[:10]:
            print(f"  [{kind}] {path}")
        if len(files) > 10:
            print(f"  ... 외 {len(files) - 10}개")
        return

    start = time.time()
    processed = 0
    skipped = 0
    errors = 0

    with get_db_connection() as conn:
        # incremental 모드: DB의 기존 hash 로딩
        existing_hashes: dict[str, str] = {}
        if args.incremental:
            existing_hashes = load_existing_hashes(conn, project)
            print(f"incremental 모드: DB 기존 파일 {len(existing_hashes)}개 hash 로드")

        for i, (path, kind) in enumerate(files):
            try:
                fhash = hash_file(path)
                # incremental 모드에서 hash 비교로 스킵 판단
                if args.incremental and existing_hashes.get(path) == fhash:
                    skipped += 1
                    continue

                text = Path(path).read_text(encoding="utf-8", errors="replace")
                original_id = upsert_original(conn, project, path, kind, text, fhash)

                chunks = split_md(text) if Path(path).suffix == ".md" else split_log(text)
                if not chunks:
                    conn.commit()
                    processed += 1
                    continue

                embeddings = embed_documents(chunks)
                insert_chunks(conn, original_id, project, path, kind, chunks, embeddings)
                conn.commit()
                processed += 1

                if (processed + skipped) % 50 == 0:
                    print(f"  {processed + skipped}/{len(files)} 처리 완료 (처리={processed}, 스킵={skipped})")
            except Exception as e:
                conn.rollback()
                print(f"  [오류] {path}: {e}")
                errors += 1

    elapsed = time.time() - start
    n = len(files)

    if args.incremental:
        print(
            f"임베딩 완료 (incremental): 전체={n}개, 처리={processed}개, 스킵={skipped}개, "
            f"오류={errors}개, {elapsed:.1f}초 소요"
        )
    else:
        print(
            f"임베딩 완료: {processed}개 처리, 오류={errors}개, {elapsed:.1f}초 소요"
            if n else "임베딩 완료: 파일 없음"
        )

    write_embed_log(
        incremental=args.incremental,
        processed=processed,
        skipped=skipped,
        errors=errors,
        elapsed=elapsed,
    )

    # drift 경고: 임베딩 완료 후 미반영 handbook이 있으면 안내 출력
    # (Phase C가 이 지점에 추가 로직을 붙일 수 있도록 지역 변수로 남김)
    try:
        drift_paths = _drift.compute_drift(project)
        if len(drift_paths) > 0:
            print(f"미반영 handbook {len(drift_paths)}개 → 갱신 권장")
        # Phase C+D1: 세션 밖 실행 시 헤드리스 Claude 자동 기동
        handbook_on = PROJECTS[project].get("auto_handbook_update", False)
        catalog_on = PROJECTS[project].get("auto_catalog_update", False)
        entry = auto_update.should_auto_launch(os.environ, handbook_on, catalog_on, len(drift_paths))
        if entry:
            cwd = os.environ.get("LOREGIST_CWD", os.getcwd())
            result = auto_update.launch_headless(entry, project, cwd)
            auto_update.report_log(result)
    except Exception:
        pass


if __name__ == "__main__":
    main()

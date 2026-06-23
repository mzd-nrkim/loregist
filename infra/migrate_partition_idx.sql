-- 인덱스 타입 선택 근거: DB 접근 불가로 실측 row 수 확인 불가 — 파티션 신규 생성 직후이므로 데이터가 없거나 극소량이라 IVFFlat lists=1 로 작성(데이터 적재 후 lists=100 재생성 가능).
-- CONCURRENTLY 사용으로 BEGIN/COMMIT 블록 없이 실행해야 함.

-- 2025-01
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_01 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_01 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_01 (project);

-- 2025-02
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_02 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_02 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_02 (project);

-- 2025-03
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_03 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_03 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_03 (project);

-- 2025-04
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_04 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_04 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_04 (project);

-- 2025-05
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_05 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_05 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_05 (project);

-- 2025-06
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_06 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_06 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_06 (project);

-- 2025-07
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_07 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_07 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_07 (project);

-- 2025-08
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_08 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_08 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_08 (project);

-- 2025-09
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_09 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_09 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_09 (project);

-- 2025-10
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_10 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_10 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_10 (project);

-- 2025-11
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_11 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_11 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_11 (project);

-- 2025-12
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_12 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_12 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2025_12 (project);

-- 2026-01
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_01 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_01 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_01 (project);

-- 2026-02
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_02 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_02 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_02 (project);

-- 2026-03
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_03 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_03 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_03 (project);

-- 2026-04
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_04 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_04 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_04 (project);

-- 2026-05
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_05 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_05 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_05 (project);

-- 2026-06 (init.sql에 이미 파티션 정의된 현재 월)
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_06 USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_06 USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_2026_06 (project);

-- DEFAULT 파티션
CREATE INDEX CONCURRENTLY ON doc_chunks_default USING ivfflat (embedding vector_cosine_ops) WITH (lists=1);
CREATE INDEX CONCURRENTLY ON doc_chunks_default USING gin (chunk_text gin_bigm_ops);
CREATE INDEX CONCURRENTLY ON doc_chunks_default (project);

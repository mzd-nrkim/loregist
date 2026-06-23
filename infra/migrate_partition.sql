BEGIN;

-- 1. 기존 테이블 보존
ALTER TABLE doc_chunks RENAME TO doc_chunks_legacy;
-- 기존 시퀀스도 rename해 신규 SERIAL 생성과 충돌 방지
ALTER SEQUENCE doc_chunks_id_seq RENAME TO doc_chunks_legacy_id_seq;

-- 2. 파티션 부모 테이블 생성
--    - PRIMARY KEY에 파티션 키(created_at) 포함 필수
--    - UNIQUE에도 파티션 키(created_at) 포함 필수
--    - FK original_id REFERENCES doc_originals(id) 유지
CREATE TABLE doc_chunks (
    id SERIAL,
    original_id INTEGER REFERENCES doc_originals(id),
    project TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    chunk_hash TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (id, created_at),
    UNIQUE (project, source_path, chunk_hash, created_at)
) PARTITION BY RANGE (created_at);

-- 3. DEFAULT 파티션
CREATE TABLE doc_chunks_default PARTITION OF doc_chunks DEFAULT;

-- 4. 과거 파티션 소급 생성 (2025-01 ~ 2026-06)
CREATE TABLE doc_chunks_2025_01 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE doc_chunks_2025_02 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

CREATE TABLE doc_chunks_2025_03 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');

CREATE TABLE doc_chunks_2025_04 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');

CREATE TABLE doc_chunks_2025_05 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');

CREATE TABLE doc_chunks_2025_06 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

CREATE TABLE doc_chunks_2025_07 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');

CREATE TABLE doc_chunks_2025_08 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');

CREATE TABLE doc_chunks_2025_09 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');

CREATE TABLE doc_chunks_2025_10 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

CREATE TABLE doc_chunks_2025_11 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

CREATE TABLE doc_chunks_2025_12 PARTITION OF doc_chunks
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');

CREATE TABLE doc_chunks_2026_01 PARTITION OF doc_chunks
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE doc_chunks_2026_02 PARTITION OF doc_chunks
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE doc_chunks_2026_03 PARTITION OF doc_chunks
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE doc_chunks_2026_04 PARTITION OF doc_chunks
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE doc_chunks_2026_05 PARTITION OF doc_chunks
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE doc_chunks_2026_06 PARTITION OF doc_chunks
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

-- 5. 데이터 이전
INSERT INTO doc_chunks SELECT * FROM doc_chunks_legacy;

-- 신규 시퀀스 값을 레거시 max(id) 이후로 설정
SELECT setval('doc_chunks_id_seq', (SELECT MAX(id) FROM doc_chunks_legacy));

-- 6. 레거시 삭제 (시퀀스도 함께 삭제)
DROP TABLE doc_chunks_legacy;
DROP SEQUENCE IF EXISTS doc_chunks_legacy_id_seq;

COMMIT;

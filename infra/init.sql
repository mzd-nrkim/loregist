-- schema version: 1
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_bigm;

CREATE TABLE doc_originals (
    id SERIAL PRIMARY KEY,
    project TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    full_text TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(project, source_path)
);

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

CREATE TABLE doc_chunks_default PARTITION OF doc_chunks DEFAULT;

CREATE TABLE doc_chunks_2026_06 PARTITION OF doc_chunks
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

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
    id SERIAL PRIMARY KEY,
    original_id INTEGER REFERENCES doc_originals(id),
    project TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    chunk_hash TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(project, source_path, chunk_hash)
);

CREATE INDEX idx_chunks_embedding ON doc_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_chunks_project ON doc_chunks (project);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_chunk_text_bigm
    ON doc_chunks USING gin (chunk_text gin_bigm_ops);

-- Migration: doc_chunks에 chunk_index 컬럼 추가
-- 기존 DB에 적용 시 사용. init.sql에는 이미 반영됨.
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS chunk_index INTEGER DEFAULT 0;

-- project 컬럼 값 loregist → stashdex 마이그레이션
-- stashdex DB에서 실행 (migrate_rename_db.sql 적용 후)
BEGIN;

UPDATE doc_originals SET project = 'stashdex' WHERE project = 'loregist';
UPDATE doc_chunks    SET project = 'stashdex' WHERE project = 'loregist';

-- 검증: loregist 잔존 0건이어야 정상
-- SELECT count(*) FROM doc_originals WHERE project = 'loregist';
-- SELECT count(*) FROM doc_chunks    WHERE project = 'loregist';

COMMIT;

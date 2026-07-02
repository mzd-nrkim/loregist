-- loregist → stashdex DB·role rename 마이그레이션
-- 전제: 활성 세션 없음, PostgreSQL superuser로 실행
-- 백업 관례: DB 변경 전후 pg_dump -Fc로 infra/backups/<ISO타임스탬프>.dump에 저장
-- 트랜잭션 밖에서 실행해야 함 (ALTER DATABASE/ROLE은 트랜잭션 비지원)
-- 멱등: stashdex DB/role이 이미 존재하면 에러 발생 → 수동 확인 후 재실행

-- 1. DB rename (기존 데이터·볼륨 보존)
ALTER DATABASE loregist RENAME TO stashdex;

-- 2. role rename
ALTER ROLE loregist RENAME TO stashdex;

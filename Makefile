PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest
PYTHONPATH_SRC := PYTHONPATH=src
PROJECT ?= demo

.PHONY: test test-unit test-int test-all help db-up db-down rotate rotate-dry setup

help:
	@echo "사용법:"
	@echo "  make test-unit        유닛 테스트만 (DB 불필요)"
	@echo "  make test-int         통합 테스트 (pgvector DB 기동 필요)"
	@echo "  make test-all         전체 + 커버리지"
	@echo "  make test             test-unit 별칭"
	@echo "  make db-up            pgvector 컨테이너 기동"
	@echo "  make db-down          pgvector 컨테이너 중지"
	@echo "  make rotate-dry       현재 rotate 대상 미리보기"
	@echo "  make rotate           날짜폴더 → vault 실이동 (PROJECT=<키> 지정 필요)"
	@echo "  make embed PROJECT=<키>   지정 프로젝트 임베딩"

setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip -q
	.venv/bin/pip install -r requirements.txt -q
	$(MAKE) db-up
	@echo "setup 완료. 다음 단계: make embed-dry"

test: test-unit

test-unit:
	$(PYTEST) -m unit -v

test-int:
	$(PYTEST) -m integration -v

test-all:
	$(PYTEST) -v --cov=. --cov-report=term-missing

embed:
	$(PYTHONPATH_SRC) $(PYTHON) -m loregist.embed --project $(PROJECT)

embed-dry:
	$(PYTHONPATH_SRC) $(PYTHON) -m loregist.embed --project $(PROJECT) --dry-run

rotate-dry:
	$(PYTHONPATH_SRC) $(PYTHON) -m loregist.rotate --project $(PROJECT) --dry-run

rotate:
	$(PYTHONPATH_SRC) $(PYTHON) -m loregist.rotate --project $(PROJECT)

db-up:
	docker compose -f infra/docker-compose.yml up -d

db-down:
	docker compose -f infra/docker-compose.yml down

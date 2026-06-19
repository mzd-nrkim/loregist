# loregist

개인 repo 문서·로그 컨텍스트 검색 인프라.  
LLM이 repo 전체를 무차별 탐색하지 않도록 pgvector 기반 시맨틱 검색 계층을 제공한다.

## Prerequisites

다음 도구가 설치되어 있어야 한다.

| 도구 | 최소 버전 | 설치 링크 |
|------|-----------|-----------|
| Git | 2.x | https://git-scm.com/downloads |
| Docker Engine | 20+ | https://docs.docker.com/engine/install/ |
| Python | 3.11+ | https://www.python.org/downloads/ |
| Make | - | OS 패키지 관리자(brew / apt / dnf 등)로 설치 |

## Quick Start

```bash
# 1. 저장소 클론
git clone <repo-url> && cd loregist

# 2. 환경변수 설정 (로컬 기본값으로 바로 실행 가능, 필요 시 수정)
cp .env.example .env

# 3. 전체 셋업: venv 생성 + 의존성 설치 + Docker 컨테이너 기동 + 임베딩 모델 다운로드
make setup

# 4. 문서 임베딩
loregist embed

# 5. 검색
loregist search "찾을 내용"
```

`make setup` 한 번으로 venv 생성, `pip install`, `docker compose up`, 임베딩 모델 다운로드까지 완료된다.

## 기업망 SSL 우회

사내 SSL inspection 환경에서 HuggingFace 모델 다운로드가 막힐 경우 아래 환경변수를 설정한다.

```bash
export LOREGIST_NO_SSL_VERIFY=1
make setup
```

`.env` 파일에 `LOREGIST_NO_SSL_VERIFY=1` 을 추가해 영구 적용할 수도 있다.  
모델이 로컬 `models/` 에 캐시된 이후에는 이 설정 없이도 동작한다.

## 디렉터리 구조

```
loregist/
├── src/loregist/      # Python 패키지 (config, embed, search, rotate, chunking, tui)
├── infra/              # Docker Compose + init.sql 스키마
├── models/             # 임베딩 모델 캐시 (multilingual-e5-small-ko-v2, ~450MB)
├── plans/              # 진행 중 계획서
├── tests/              # 단위/통합 테스트
├── projects.toml       # 프로젝트 레지스트리
├── Makefile            # 편의 명령
└── .env.example        # 환경변수 예시
```

## 명령어 요약

```bash
# 임베딩
loregist embed                          # 현재 프로젝트 전체 임베딩
loregist embed --dry-run                # 대상 파일 목록만 출력
loregist embed --incremental            # 변경된 파일만 임베딩

# 검색
loregist search "쿼리"                  # hybrid 모드 (기본)
loregist search "쿼리" --mode fts       # 키워드 검색
loregist search "쿼리" --all-projects   # 전체 프로젝트
loregist search "쿼리" --top-k 10

# 프로젝트
loregist projects --json                # 등록 프로젝트 목록
loregist projects --current             # 현재 프로젝트 키

# 라이프사이클
loregist rotate --dry-run               # 이동 대상 미리보기
loregist rotate                         # vault 이동 실행

# 개발/운영
make test-unit      # 단위 테스트 (DB 불필요)
make test-int       # 통합 테스트 (pgvector 필요)
make db-up          # pgvector 컨테이너 기동
make db-down        # pgvector 컨테이너 중지
```

## 새 프로젝트 추가

`projects.toml`에 블록 추가 후 `loregist embed --project <키>` 실행.  
자세한 사항은 `CLAUDE.md` 참조.

## DB 연결 정보

pgAdmin 등 외부 도구로 직접 접속할 때:

| 항목 | 값 |
|------|----|
| Host | `localhost` |
| Port | `5433` |
| Database | `loregist` |
| Username | `loregist` |
| Password | `vector_local` (로컬 기본값 — `.env`의 `LOREGIST_DB_PASSWORD`로 변경 가능) |

주요 테이블: `doc_originals`(원문), `doc_chunks`(임베딩 청크)

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LOREGIST_DB_PASSWORD` | `vector_local` | PostgreSQL 비밀번호 (로컬 기본값) |
| `LOREGIST_WORKSPACE` | `~/workspace` | 작업 루트 경로 |
| `LOREGIST_NO_SSL_VERIFY` | `0` | 기업망 SSL inspection 우회 (1=활성) |

## 롤백

```bash
docker compose -f infra/docker-compose.yml down -v
```

vault 원본과 `doc_originals.full_text` 가 남아 있어 데이터 손실 없이 재구축 가능.

## License

MIT — see [LICENSE](LICENSE)

# stashdex 명령어 레퍼런스

→ [USAGE.md](USAGE.md)

---

## 명령어 요약

```bash
# 임베딩
stashdex embed                          # 현재 프로젝트 전체 임베딩
stashdex embed --dry-run                # 대상 파일 목록만 출력
stashdex embed --incremental            # 변경된 파일만 임베딩

# 검색
stashdex search "쿼리"                  # hybrid 모드 (기본)
stashdex search "쿼리" --mode fts       # 키워드 검색 (vector / fts / like / hybrid)
stashdex search "쿼리" --all-projects   # 전체 프로젝트
stashdex search "쿼리" --top-k 10
stashdex search "쿼리" --json           # 구조화 출력 (스크립팅용)
stashdex search "쿼리" --open 1         # 1번 결과 즉시 기본 앱으로 열기
stashdex search "쿼리" --strategy cascade            # wiki→hot→cold 다단계 (조기종료)
stashdex search "쿼리" --strategy fusion --wiki-boost 1.5  # 전 계층 동시 검색 + wiki 가중
stashdex search "쿼리" --cascade-threshold 0.85      # cascade 조기종료 임계값 (기본 0.80)
stashdex search "쿼리" --tier m3                     # 최근 3개월 윈도우 우선 (m1/m3/m6/m12/auto)
stashdex similar <파일경로>             # 지정 파일과 벡터 유사도 높은 과거 문서 검색 (전 프로젝트, top-k 기본 5)
stashdex similar <파일경로> --top-k 10  # 유사 문서 상위 N개 반환

# 프로젝트
stashdex project list                   # 등록 프로젝트 목록
stashdex project current                # 현재 프로젝트 키

# 기록
stashdex journal "메시지"               # 오늘 날짜 로그 파일에 타임스탬프 기록
stashdex watch                          # 현재 프로젝트 vault 감시 (파일 변경 시 자동 embed)
stashdex watch --dir ~/notes            # 특정 디렉터리 감시

# 라이프사이클
stashdex rotate --dry-run               # 이동 대상 미리보기
stashdex rotate                         # vault 이동 실행 (대상 확장자: projects.toml extensions, 기본 md·log·txt)
stashdex rotate --extensions md,log,txt # 확장자 런타임 override (우선순위: CLI > projects.toml > 기본값)
# ⚠️  vault-cleanup: 파괴적 opt-in — projects.toml에 vault_cleanup 키 설정 필수, 삭제는 비가역(파일 unlink)
stashdex vault-cleanup --project <키> --dry-run   # 정리 대상 미리보기 (기본값, 실제 삭제 없음)
stashdex vault-cleanup --project <키> --apply     # 실제 삭제 실행 (--apply 명시 필수, DB full_text는 보존)

# catalog
stashdex catalog-init --project {p}     # _wiki/ 초기화 (최초 1회)
stashdex catalog --project {p}          # TOPICS.md·DECISIONS.md 자동 갱신

# 개발/운영
stashdex status                         # 프로젝트별 임베딩 청크 수·최종 임베딩 시각·vault 경로 대시보드 출력 (DB 연결 진단 겸용)
make test-unit      # 단위 테스트 (DB 불필요)
make test-int       # 통합 테스트 (pgvector 필요)
make db-up          # pgvector 컨테이너 기동
make db-down        # pgvector 컨테이너 중지
```

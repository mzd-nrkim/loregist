# projects.toml 설정 가이드

→ [USAGE.md](USAGE.md)

---

## 프로젝트 블록 설정

```toml
# 일반 프로젝트: 작업문서(docs_root) + 로그(vault) + 콜드 스토리지(cold)
[projects.myproject]
docs_root     = "path/to/myproject/dev"
vault         = "logvault/myproject"
cold          = "logvault/myproject/cold"
catalog       = true   # _wiki/ 인덱스 사용 시
extensions    = ["md", "log", "txt"]   # 임베딩·watch·vault-cleanup 대상 확장자 (기본값: ["md","log","txt"], dot 없이 작성)
vault_cleanup = true   # cold+vault 오래된 파일 삭제 opt-in (기본 90일 보존, 미설정 시 삭제 안 함)
# vault_cleanup = 30   # 일수 직접 지정 가능
# hot_days = 3         # rotate 기준일 override (기본 7일, 미설정 시 전역값 사용)

# plans/done 로테이션만 필요한 경우
[projects.myproject]
vault = "logvault/myproject"
done  = "path/to/myproject/plans/done"

# handbook: 감시·참조할 위키 파일·디렉터리 목록 (wiki_sources는 deprecated, handbook 사용 권장)
# 문자열 단축형(path만)과 inline table({path, writable, update_when}) 혼용 가능
[projects.myproject]
docs_root = "path/to/myproject/dev"
vault     = "logvault/myproject"
handbook  = [
  "path/to/ref-doc.md",                                        # 문자열 단축형 (path만, writable=false)
  {path = "path/to/auto-updated.md", writable = true},         # 쓰기 허용
  {path = "path/to/trigger.md", writable = true, update_when = "명령어 추가·변경 시"},  # 업데이트 트리거 조건 명시
]
# handbook 스키마:
#   path        (필수): 파일·디렉터리 경로. WORKSPACE 상대 또는 절대경로, glob 가능.
#   writable    (선택, 기본 false): 자동 업데이트(쓰기) 허용 여부.
#   update_when (선택, 기본 null): 업데이트 트리거 조건 문자열.
#
# catalog 암묵 활성화:
#   catalog 키 미설정 + wiki 1건 이상 + docs_root 존재 → {docs_root}/_wiki 자동 설정
#   catalog 경로를 커스텀하려면 catalog = "경로" 명시
```

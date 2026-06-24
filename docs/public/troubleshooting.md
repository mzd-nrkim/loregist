# 트러블슈팅 기록

운영 중 마주친 에러와 원인·해결을 누적 기록한다. 새 항목은 맨 위에 추가한다.

---

## git pull 시 `published` 태그 clobber 에러 (2026-06-24)

### 증상

IDE의 git pull 버튼(내부적으로 `git pull --tags origin main` 실행) 사용 시 다음 에러 발생:

```
From github.com:your-org/your-repo
 * branch            main       -> FETCH_HEAD
 ! [rejected]        published  -> published  (would clobber existing tag)
```

브랜치(`main -> FETCH_HEAD`)는 정상 fetch되고, **태그 갱신만 실패**한다.

### 원인

- `published`는 **배포마다 최신 커밋으로 옮겨지는 "움직이는 태그(moving tag)"**다(브랜치처럼 쓰이는데 태그로 생성됨).
- `git pull --tags`는 원격의 모든 태그를 가져오려 한다.
- 로컬 `published` 태그와 원격 `published` 태그가 **서로 다른 커밋**을 가리킨다.
- Git은 태그를 불변(immutable)으로 취급하므로, 기존 로컬 태그를 덮어쓰는 것을 안전상 거부한다 → `[rejected] ... would clobber existing tag`.
- 즉 다른 세션/배포가 원격 `published`를 전진시키면, 로컬에서 pull할 때마다 충돌이 재발한다. **사용자 조작 실수가 아니다.**

실제 사례:
- 로컬 `published` = `f4bd846` (2026-06-23, "merge(publish): tree-sync 제외정합...")
- 원격 `published` = `fe30a41` (2026-06-24, "feat(handbook-update): enrichment 기본화...")
- 로컬이 원격의 **조상**(`git merge-base --is-ancestor` YES) → 원격이 명백히 최신, 손실 없이 갱신 가능.

### 해결

로컬 태그를 원격에 강제로 맞춘다(움직이는 태그이므로 force가 정상 동작):

```bash
git fetch --tags --force origin
```

또는 로컬 태그를 지우고 다시 받기:

```bash
git tag -d published
git fetch origin tag published
```

### 안전 확인 절차 (force 전)

덮어쓰기 전, 로컬 태그가 원격 태그의 조상인지 확인하면 손실 없음을 보장할 수 있다:

```bash
git merge-base --is-ancestor <로컬-published-커밋> <원격-published-커밋> && echo "원격이 최신, 안전"
```

### 재발 방지 / 근본 차단

- 일반 pull에는 `--tags`가 불필요하다: `git pull origin main` (태그 없이 브랜치만).
- IDE pull 설정에 "fetch tags on pull" 옵션이 있으면 끄거나 force fetch로 변경.
- 매번 뜨면 그냥 `git fetch --tags --force origin` 한 줄로 해소.

> 참고: 위험한 에러가 아니다. Git이 로컬 태그가 가리키던 커밋 정보 유실을 막으려 명시적 `--force`를 요구하는 안전장치일 뿐이다.

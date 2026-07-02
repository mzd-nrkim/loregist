# stashdex git hook 설치

`post-commit`은 `docs/dev/` 변경 커밋 시 자동으로 incremental 임베딩을 실행하는 템플릿입니다.
각 프로젝트 repo의 `.git/hooks/`에 심볼릭 링크 또는 복사로 설치하세요.

## 심볼릭 링크 (권장)

```bash
ln -sf "${STASHDEX_DIR:-/path/to/stashdex}/hooks/post-commit" \
    /path/to/project-repo/.git/hooks/post-commit
```

## 복사

```bash
cp "${STASHDEX_DIR:-/path/to/stashdex}/hooks/post-commit" \
    /path/to/project-repo/.git/hooks/post-commit
chmod +x /path/to/project-repo/.git/hooks/post-commit
```

실행 로그는 `${STASHDEX_WORKSPACE:-$HOME/workspace}/../logvault/embed-log/YYYY-MM-DD.log`에 기록됩니다.

#!/usr/bin/env bash
# 오늘 GitHub 활동(PR·이슈·커밋)을 loregist journal 로그에 append
# 의존: gh CLI (https://cli.github.com), jq
TODAY=$(date +%Y-%m-%d)
VAULT="${LOREGIST_VAULT:-$HOME/.loregist}"
OUTPUT="$VAULT/journal/$TODAY.log"
mkdir -p "$(dirname "$OUTPUT")"
gh api /notifications --paginate \
  | jq -r '.[] | "[github] \(.subject.type) — \(.repository.full_name): \(.subject.title)"' \
  >> "$OUTPUT"
echo "Appended GitHub activity to $OUTPUT"

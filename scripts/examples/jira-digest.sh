#!/usr/bin/env bash
# 오늘 Jira 업데이트 이슈를 stashdex journal 로그에 append
# 의존: curl, jq, JIRA_URL / JIRA_TOKEN 환경변수
TODAY=$(date +%Y-%m-%d)
VAULT="${LOREGIST_VAULT:-$HOME/stashdex/vault}"
OUTPUT="$VAULT/journal/$TODAY.log"
mkdir -p "$(dirname "$OUTPUT")"
curl -s -H "Authorization: Bearer $JIRA_TOKEN" \
  "$JIRA_URL/rest/api/3/search?jql=assignee=currentUser()+AND+updated>=-1d&fields=summary,status" \
  | jq -r '.issues[] | "[jira] \(.key) [\(.fields.status.name)]: \(.fields.summary)"' \
  >> "$OUTPUT"
echo "Appended Jira activity to $OUTPUT"

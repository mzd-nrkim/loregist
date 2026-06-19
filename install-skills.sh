#!/usr/bin/env bash
# loregist 스킬을 ~/.claude/skills/에 심링크로 설치
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/.claude/skills"
SKILLS_DST="$HOME/.claude/skills"
mkdir -p "$SKILLS_DST"
for skill_dir in "$SKILLS_SRC"/*/; do
  name="$(basename "$skill_dir")"
  ln -sfn "$skill_dir" "$SKILLS_DST/$name"
  echo "linked: $name"
done

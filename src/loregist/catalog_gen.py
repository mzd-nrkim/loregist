"""
catalog_gen.py — _catalog 자동 생성·갱신 도구

사용법:
    python -m loregist.catalog_gen --project <프로젝트명>

동작:
    1. PROJECTS[project].catalog 경로 아래 *.md 파일의 YAML frontmatter를 파싱
    2. type: topic  → TOPICS.md 자동 생성 영역 렌더링
       type: decision → DECISIONS.md 자동 생성 영역 렌더링
    3. <!-- AUTO:START --> ~ <!-- AUTO:END --> 마커 사이만 덮어씀
       마커 밖 수동 텍스트는 보존됨
    4. frontmatter 없는 파일은 무시, type 누락은 경고 출력
    5. 마커 없는 파일은 경고만 출력 (수동 우선 원칙)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] pyyaml이 설치되지 않았습니다. `pip install pyyaml`", file=sys.stderr)
    sys.exit(1)

from loregist.config import PROJECTS

AUTO_START = "<!-- AUTO:START -->"
AUTO_END = "<!-- AUTO:END -->"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> "dict | None":
    """YAML frontmatter를 파싱한다. frontmatter 없으면 None 반환."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        return None


def _collect_entries(catalog_dir: Path) -> "tuple[list[dict], list[dict]]":
    """
    catalog_dir 하위 *.md 파일을 스캔해 topic/decision 목록을 반환한다.

    반환: (topics, decisions) — 각 항목은 frontmatter dict + '_file' 키 포함
    """
    topics: list[dict] = []
    decisions: list[dict] = []

    for md_file in sorted(catalog_dir.rglob("*.md")):
        # TOPICS.md / DECISIONS.md 자체는 파싱 대상에서 제외
        if md_file.name in ("TOPICS.md", "DECISIONS.md"):
            continue

        text = md_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if fm is None:
            # frontmatter 없는 파일은 무시 (경고 없음, 의도적 설계)
            continue

        doc_type = fm.get("type")
        if not doc_type:
            print(
                f"[WARN] {md_file.name}: frontmatter에 'type' 필드가 없습니다 — 건너뜀",
                file=sys.stderr,
            )
            continue

        entry = dict(fm)
        entry["_file"] = str(md_file.relative_to(catalog_dir))

        if doc_type == "topic":
            topics.append(entry)
        elif doc_type == "decision":
            decisions.append(entry)
        else:
            print(
                f"[WARN] {md_file.name}: 알 수 없는 type={doc_type!r} — 건너뜀",
                file=sys.stderr,
            )

    return topics, decisions


def _render_topics(topics: list[dict]) -> str:
    """topic 목록을 TOPICS.md 표 형식으로 렌더링."""
    lines = [
        "| id | 한줄요약 | status | tags | 관련 파일 |",
        "|----|---------|--------|------|----------|",
    ]
    for e in topics:
        tid = e.get("id", "")
        status = e.get("status", "")
        tags = ", ".join(e.get("tags") or [])
        related = ", ".join(str(r) for r in (e.get("related") or []))
        # 한줄요약: summary 필드 우선, 없으면 _file 표시
        summary = e.get("summary", e.get("title", e.get("_file", "")))
        lines.append(f"| {tid} | {summary} | {status} | {tags} | {related} |")
    return "\n".join(lines)


def _render_decisions(decisions: list[dict]) -> str:
    """decision 목록을 DECISIONS.md 표 형식으로 렌더링."""
    lines = [
        "| date | id | 결정 | 근거 (요약) | status | related |",
        "|------|----|----|------------|--------|---------|",
    ]
    # date 기준 정렬
    for e in sorted(decisions, key=lambda x: str(x.get("date", ""))):
        did = e.get("id", "")
        date = str(e.get("date", ""))
        status = e.get("status", "")
        related = ", ".join(str(r) for r in (e.get("related") or []))
        # 결정·근거: title/summary/reason 필드 순으로 fallback
        title = e.get("title", e.get("summary", e.get("_file", "")))
        reason = e.get("reason", e.get("rationale", ""))
        lines.append(f"| {date} | {did} | {title} | {reason} | {status} | {related} |")
    return "\n".join(lines)


def _update_section(content: str, new_body: str, filepath: Path) -> "str | None":
    """
    content 안의 AUTO:START ~ AUTO:END 사이를 new_body로 교체한다.
    마커가 없으면 경고를 출력하고 None을 반환한다 (파일 무수정).
    """
    if AUTO_START not in content or AUTO_END not in content:
        print(
            f"[WARN] {filepath.name}: AUTO 마커({AUTO_START} / {AUTO_END})가 없습니다 — 수정 건너뜀",
            file=sys.stderr,
        )
        return None

    before, rest = content.split(AUTO_START, 1)
    _, after = rest.split(AUTO_END, 1)
    return f"{before}{AUTO_START}\n{new_body}\n{AUTO_END}{after}"


def generate(project: str) -> None:
    """주어진 프로젝트의 _catalog를 자동 갱신한다."""
    cfg = PROJECTS.get(project)
    if cfg is None:
        print(f"[ERROR] 프로젝트 '{project}'가 PROJECTS에 없습니다.", file=sys.stderr)
        sys.exit(1)

    catalog_dir: "Path | None" = cfg.get("catalog")
    if catalog_dir is None:
        print(
            f"[INFO] 프로젝트 '{project}'는 catalog opt-in이 설정되어 있지 않습니다.\n"
            f"  projects.toml의 [{project}] 블록에 'catalog = true' 또는 경로를 추가하세요.",
            file=sys.stderr,
        )
        sys.exit(0)

    if not catalog_dir.exists():
        print(
            f"[ERROR] catalog 디렉터리가 존재하지 않습니다: {catalog_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    topics, decisions = _collect_entries(catalog_dir)

    # TOPICS.md 갱신
    topics_md = catalog_dir / "TOPICS.md"
    if topics_md.exists():
        content = topics_md.read_text(encoding="utf-8")
        updated = _update_section(content, _render_topics(topics), topics_md)
        if updated is not None:
            topics_md.write_text(updated, encoding="utf-8")
            print(f"[OK] TOPICS.md 갱신 완료 ({len(topics)}건)")
    else:
        print(f"[WARN] {topics_md} 파일이 없습니다 — TOPICS.md 갱신 건너뜀", file=sys.stderr)

    # DECISIONS.md 갱신
    decisions_md = catalog_dir / "DECISIONS.md"
    if decisions_md.exists():
        content = decisions_md.read_text(encoding="utf-8")
        updated = _update_section(content, _render_decisions(decisions), decisions_md)
        if updated is not None:
            decisions_md.write_text(updated, encoding="utf-8")
            print(f"[OK] DECISIONS.md 갱신 완료 ({len(decisions)}건)")
    else:
        print(f"[WARN] {decisions_md} 파일이 없습니다 — DECISIONS.md 갱신 건너뜀", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="_catalog TOPICS.md / DECISIONS.md 자동 생성·갱신"
    )
    parser.add_argument(
        "--project",
        required=True,
        help="대상 프로젝트 키 (projects.toml에 catalog opt-in된 프로젝트만 유효)",
    )
    args = parser.parse_args()
    generate(args.project)


if __name__ == "__main__":
    main()

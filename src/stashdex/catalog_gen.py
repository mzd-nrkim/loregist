"""
catalog_gen.py — _wiki 자동 생성·갱신 도구

사용법:
    python -m stashdex.catalog_gen run  --project <프로젝트명>
    python -m stashdex.catalog_gen init --project <프로젝트명> [--force]

동작 (run):
    1. PROJECTS[project].catalog 경로 아래 *.md 파일의 YAML frontmatter를 파싱
    2. type: topic  → TOPICS.md 자동 생성 영역 렌더링
       type: decision → DECISIONS.md 자동 생성 영역 렌더링
    3. <!-- AUTO:START --> ~ <!-- AUTO:END --> 마커 사이만 덮어씀
       마커 밖 수동 텍스트는 보존됨
    4. frontmatter 없는 파일은 무시, type 누락은 경고 출력
    5. 마커 없는 파일은 경고만 출력 (수동 우선 원칙)

동작 (init):
    1. _wiki/ 디렉터리 생성 (없으면 생성)
    2. TOPICS.md / DECISIONS.md 템플릿 생성 (이미 존재 시 스킵, --force 시 덮어씀)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] pyyaml이 설치되지 않았습니다. `pip install pyyaml`", file=sys.stderr)
    sys.exit(1)

from stashdex.config import PROJECTS

AUTO_START = "<!-- AUTO:START -->"
AUTO_END = "<!-- AUTO:END -->"

# ──────────────────────────────────────────────────────────────
# init 서브커맨드용 템플릿 상수
# ──────────────────────────────────────────────────────────────

_TMPL_TOPICS = """\
---
id: topics-index
type: index
date: {date}
---
# TOPICS — {project}

프로젝트 주요 주제 인덱스. 반복 등장하는 도메인 개념·기술 영역을 정리한다.

| id | 한줄요약 | 관련 문서 |
|---|---|---|

<!-- AUTO:START -->
<!-- AUTO:END -->
"""

_TMPL_DECISIONS = """\
---
id: decisions-index
type: index
date: {date}
---
# DECISIONS — {project}

프로젝트 주요 의사결정 인덱스. 아키텍처·기술 선택·정책 변경을 기록한다.

| date | id | 결정 | 근거 (요약) | status |
|---|---|---|---|---|

<!-- AUTO:START -->
<!-- AUTO:END -->
"""

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
        "| id | 한줄요약 | status | tags | 관련 파일 | 연결 |",
        "|----|---------|--------|------|----------|------|",
    ]
    for e in topics:
        tid = e.get("id", "")
        status = e.get("status", "")
        tags = ", ".join(e.get("tags") or [])
        related = ", ".join(str(r) for r in (e.get("related") or []))
        edges_str = ", ".join(str(eg) for eg in (e.get("edges") or []))
        # 한줄요약: summary 필드 우선, 없으면 _file 표시
        summary = e.get("summary", e.get("title", e.get("_file", "")))
        lines.append(f"| {tid} | {summary} | {status} | {tags} | {related} | {edges_str} |")
    return "\n".join(lines)


def _render_decisions(decisions: list[dict]) -> str:
    """decision 목록을 DECISIONS.md 표 형식으로 렌더링."""
    lines = [
        "| date | id | 결정 | 근거 (요약) | status | related | 연결 |",
        "|------|----|----|------------|--------|---------|------|",
    ]
    # date 기준 정렬
    for e in sorted(decisions, key=lambda x: str(x.get("date", ""))):
        did = e.get("id", "")
        date = str(e.get("date", ""))
        status = e.get("status", "")
        related = ", ".join(str(r) for r in (e.get("related") or []))
        edges_str = ", ".join(str(eg) for eg in (e.get("edges") or []))
        # 결정·근거: title/summary/reason 필드 순으로 fallback
        title = e.get("title", e.get("summary", e.get("_file", "")))
        reason = e.get("reason", e.get("rationale", ""))
        lines.append(f"| {date} | {did} | {title} | {reason} | {status} | {related} | {edges_str} |")
    return "\n".join(lines)


def _render_overview(topics: list[dict], decisions: list[dict]) -> str:
    """topics·decisions 요약을 README overview 마크다운으로 렌더링."""
    today = date.today().isoformat()
    header = (
        f"> **최근 갱신**: {today} · "
        f"**Topics**: {len(topics)}건 · "
        f"**Decisions**: {len(decisions)}건"
    )

    def _links(entries: list[dict]) -> str:
        if not entries:
            return "없음"
        return ", ".join(
            f"[{e.get('id', e.get('_file', ''))}]({e.get('_file', '')})"
            for e in entries
        )

    table = (
        "| 구분 | 목록 |\n"
        "|---|---|\n"
        f"| Topics | {_links(topics)} |\n"
        f"| Decisions | {_links(decisions)} |"
    )
    return f"{header}\n\n{table}"


def _update_heading_section(content: str, heading: str, new_body: str) -> str:
    """
    content 안의 `## {heading}` 섹션을 new_body로 교체한다.
    헤딩이 없으면 문서 끝에 추가한다.
    """
    pattern = re.compile(
        r"(^## " + re.escape(heading) + r"\s*\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    replacement = rf"\g<1>{new_body}\n"
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        # 헤딩 없음 → 문서 끝에 추가
        new_content = content.rstrip("\n") + f"\n\n## {heading}\n\n{new_body}\n"
    return new_content


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


def _write_template(path: Path, project: str, kind: str, today: str) -> None:
    """
    kind 에 따라 TOPICS 또는 DECISIONS 템플릿을 path 에 기록한다.

    Args:
        path:    대상 파일 경로
        project: 프로젝트 키 (템플릿 {project} placeholder 치환용)
        kind:    "TOPICS" 또는 "DECISIONS"
        today:   날짜 문자열 (YYYY-MM-DD)
    """
    if kind == "TOPICS":
        rendered = _TMPL_TOPICS.format(project=project, date=today)
    elif kind == "DECISIONS":
        rendered = _TMPL_DECISIONS.format(project=project, date=today)
    else:
        raise ValueError(f"알 수 없는 kind: {kind!r}")
    path.write_text(rendered, encoding="utf-8")


def init_catalog(project: str, force: bool = False) -> None:
    """
    _wiki/ 디렉터리와 TOPICS.md·DECISIONS.md 템플릿을 초기화한다.

    - 이미 파일이 존재하고 force=False → [SKIP] 출력, 건너뜀
    - force=True → 덮어씀
    - 완료 후 "생성 N건 / 스킵 M건" 요약 출력
    """
    cfg = PROJECTS.get(project)
    if cfg is None:
        print(f"[ERROR] 프로젝트 '{project}'가 PROJECTS에 없습니다.", file=sys.stderr)
        sys.exit(1)

    catalog_dir: "Path | None" = cfg.get("catalog")
    if not catalog_dir:
        print(
            f"[INFO] 프로젝트 '{project}'는 catalog opt-in이 설정되어 있지 않습니다.\n"
            f"  projects.toml의 [{project}] 블록에 'catalog = true' 또는 경로를 추가하세요.",
            file=sys.stderr,
        )
        sys.exit(0)

    catalog_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    created = 0
    skipped = 0

    for kind in ("TOPICS", "DECISIONS"):
        path = catalog_dir / f"{kind}.md"
        if path.exists() and not force:
            print(f"[SKIP] {path.name} 이미 존재합니다 (--force 로 덮어쓸 수 있습니다).")
            skipped += 1
        else:
            _write_template(path, project, kind, today)
            print(f"[OK] {path.name} 생성 완료.")
            created += 1

    print(f"완료: 생성 {created}건 / 스킵 {skipped}건")


def generate(project: str) -> None:
    """주어진 프로젝트의 _wiki를 자동 갱신한다."""
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
    wrote_any = False  # 실제 파일 반영이 1건이라도 있었는지 — 스탬프 전진 조건

    # TOPICS.md 갱신
    topics_md = catalog_dir / "TOPICS.md"
    if topics_md.exists():
        content = topics_md.read_text(encoding="utf-8")
        updated = _update_section(content, _render_topics(topics), topics_md)
        if updated is not None and updated != content:
            topics_md.write_text(updated, encoding="utf-8")
            wrote_any = True
            print(f"[OK] TOPICS.md 갱신 완료 ({len(topics)}건)")
    else:
        print(f"[WARN] {topics_md} 파일이 없습니다 — TOPICS.md 갱신 건너뜀", file=sys.stderr)

    # DECISIONS.md 갱신
    decisions_md = catalog_dir / "DECISIONS.md"
    if decisions_md.exists():
        content = decisions_md.read_text(encoding="utf-8")
        updated = _update_section(content, _render_decisions(decisions), decisions_md)
        if updated is not None and updated != content:
            decisions_md.write_text(updated, encoding="utf-8")
            wrote_any = True
            print(f"[OK] DECISIONS.md 갱신 완료 ({len(decisions)}건)")
    else:
        print(f"[WARN] {decisions_md} 파일이 없습니다 — DECISIONS.md 갱신 건너뜀", file=sys.stderr)

    # README overview (선택 기능 — catalog_readme 선언 시만)
    catalog_readme_path = cfg.get("catalog_readme")
    if catalog_readme_path is not None:
        if catalog_readme_path.exists():
            readme_content = catalog_readme_path.read_text(encoding="utf-8")
            overview_body = _render_overview(topics, decisions)
            updated_readme = _update_heading_section(readme_content, "카탈로그 개요", overview_body)
            if updated_readme != readme_content:
                catalog_readme_path.write_text(updated_readme, encoding="utf-8")
                wrote_any = True
                print(f"[OK] {catalog_readme_path.name} catalog overview 갱신 완료")
        else:
            print(
                f"[WARN] catalog_readme 경로가 존재하지 않습니다: {catalog_readme_path}",
                file=sys.stderr,
            )

    # 실제 반영이 1건이라도 있었을 때만 스탬프를 전진시킨다.
    # 변경 0건이면 기존 스탬프를 유지해 미반영 handbook이 drift 추적에서 사면되는 것을 막는다.
    if wrote_any:
        try:
            sha = subprocess.check_output(
                ["git", "-C", str(catalog_dir), "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            stamp = sha
        except Exception:
            stamp = datetime.now().isoformat()
        (catalog_dir / ".last_catalog_update").write_text(stamp, encoding="utf-8")


def lint_edges(project: str, as_json: bool = False) -> tuple[int, int]:
    """
    _wiki/ 카탈로그 파일들의 edges 필드 무결성을 검사한다.

    검사 규칙:
    - dangling (error): edges의 id가 실존 카탈로그 id 집합에 없음
    - asymmetric (error): A→B인데 B→A 역엣지 없음
    - self-ref (error): 자기 id를 edges에 포함
    - orphan (warning): edges 비어있고 피참조도 없음

    반환: (error_count, warning_count)
    """
    import json as _json

    cfg = PROJECTS.get(project)
    if cfg is None:
        print(f"[ERROR] 프로젝트 '{project}'가 PROJECTS에 없습니다.", file=sys.stderr)
        sys.exit(1)

    catalog_dir: "Path | None" = cfg.get("catalog")
    if catalog_dir is None:
        print(
            f"[INFO] 프로젝트 '{project}'는 catalog opt-in이 설정되어 있지 않습니다.",
            file=sys.stderr,
        )
        sys.exit(0)

    if not catalog_dir.exists():
        print(
            f"[ERROR] catalog 디렉터리가 존재하지 않습니다: {catalog_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 모든 .md 파일 파싱 (TOPICS.md / DECISIONS.md 제외)
    # id → edges 매핑 수집
    id_to_edges: dict[str, list[str]] = {}

    for md_file in sorted(catalog_dir.rglob("*.md")):
        if md_file.name in ("TOPICS.md", "DECISIONS.md"):
            continue
        text = md_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if fm is None:
            continue
        doc_id = fm.get("id")
        if not doc_id:
            continue
        raw_edges = fm.get("edges")
        if raw_edges is None:
            edges: list[str] = []
        elif isinstance(raw_edges, list):
            edges = [str(e) for e in raw_edges]
        else:
            edges = []
        id_to_edges[str(doc_id)] = edges

    # 실존 id 집합
    all_ids: set[str] = set(id_to_edges.keys())

    # 피참조 집합 (누군가의 edges에 등장한 id)
    referenced_ids: set[str] = set()
    for edges in id_to_edges.values():
        referenced_ids.update(edges)

    errors: list[dict] = []
    warnings: list[dict] = []

    for src_id, edges in id_to_edges.items():
        # orphan 검사 (warning): edges 비어있고 피참조도 없음
        if not edges and src_id not in referenced_ids:
            msg = f"{src_id} — edges 비어있고 피참조 없음"
            print(f"[WARN] orphan: {msg}")
            warnings.append({"rule": "orphan", "id": src_id, "message": msg})
            continue

        for edge_id in edges:
            # self-ref 검사
            if edge_id == src_id:
                msg = f"{src_id}.edges에 {src_id} 자기 참조"
                print(f"[LINT] self-ref: {msg}")
                errors.append({"rule": "self-ref", "id": src_id, "message": msg})
                continue

            # dangling 검사
            if edge_id not in all_ids:
                msg = f"{src_id}.edges[]='{edge_id}' — 존재하지 않는 id"
                print(f"[LINT] dangling: {msg}")
                errors.append({"rule": "dangling", "id": src_id, "message": msg})
                continue

            # asymmetric 검사
            if src_id not in id_to_edges.get(edge_id, []):
                suggestion = f"{edge_id}의 edges에 {src_id} 추가 필요"
                msg = f"{src_id}→{edge_id} 이지만 {edge_id}.edges에 {src_id} 없음 (제안: {suggestion})"
                print(f"[LINT] asymmetric: {msg}")
                errors.append({
                    "rule": "asymmetric",
                    "id": src_id,
                    "message": msg,
                    "suggestion": suggestion,
                })

    error_count = len(errors)
    warning_count = len(warnings)
    print(f"[LINT] error {error_count}건, warning {warning_count}건")

    if as_json:
        result = {
            "errors": errors,
            "warnings": warnings,
            "error_count": error_count,
            "warning_count": warning_count,
        }
        print(_json.dumps(result, ensure_ascii=False, indent=2))

    return error_count, warning_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="_wiki TOPICS.md / DECISIONS.md 자동 생성·갱신"
    )
    subparsers = parser.add_subparsers(dest="subcmd", required=True)

    # run 서브커맨드 (기존 동작)
    sub_run = subparsers.add_parser(
        "run",
        help="_wiki 자동 갱신 (TOPICS.md·DECISIONS.md 재생성)",
    )
    sub_run.add_argument(
        "--project",
        required=True,
        help="대상 프로젝트 키 (projects.toml에 catalog opt-in된 프로젝트만 유효)",
    )
    sub_run.add_argument(
        "--lint",
        action="store_true",
        default=False,
        help="generate 대신 edges 무결성 lint 실행",
    )
    sub_run.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        default=False,
        help="lint 결과를 JSON으로도 출력 (--lint와 함께 사용)",
    )

    # init 서브커맨드 (신규)
    sub_init = subparsers.add_parser(
        "init",
        help="_wiki/ 디렉터리와 TOPICS.md·DECISIONS.md 템플릿 초기화",
    )
    sub_init.add_argument(
        "--project",
        required=True,
        help="대상 프로젝트 키",
    )
    sub_init.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="이미 존재하는 파일도 덮어씀",
    )

    args = parser.parse_args()

    if args.subcmd == "run":
        if args.lint:
            error_count, _ = lint_edges(args.project, as_json=args.as_json)
            if error_count > 0:
                sys.exit(1)
        else:
            generate(args.project)
    elif args.subcmd == "init":
        init_catalog(args.project, args.force)


if __name__ == "__main__":
    main()

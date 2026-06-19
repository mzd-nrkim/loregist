#!/usr/bin/env python
"""터미널 UX 헬퍼: 단계별 스피너 + 색상 멀티라인 검색결과 렌더 + 기본앱 오픈.

설계: 비-TTY(파이프/테스트/리다이렉트)에서는 색상·애니메이션·인터랙션을 모두 끄고
search.py가 기존 plain 포맷을 쓰도록 둔다. 여기 함수들은 TTY 경로 전용이다.
"""
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

# ── ANSI 색상 ──────────────────────────────────────────────
_RESET = "\033[0m"
_CODES = {
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
    "bgyellow": "\033[30;43m",
}


def color_enabled(stream=sys.stdout) -> bool:
    """색상 출력 가능 여부. NO_COLOR 존중 + TTY 판정."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("LOREGIST_FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def c(text: str, *styles: str, enabled: bool = True) -> str:
    if not enabled or not styles:
        return text
    prefix = "".join(_CODES.get(s, "") for s in styles)
    return f"{prefix}{text}{_RESET}"


# ── 단계별 스피너 ──────────────────────────────────────────
_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Spinner:
    """stderr에 단계별 braille 스피너를 그린다. TTY가 아니면 완전 무동작.

    사용:
        sp = Spinner(enabled=...)
        with sp.step("모델 로딩"):
            ...
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled and bool(getattr(sys.stderr, "isatty", lambda: False)())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._label = ""

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = _FRAMES[i % len(_FRAMES)]
            sys.stderr.write(f"\r{c(frame, 'cyan')} {self._label}\033[K")
            sys.stderr.flush()
            i += 1
            time.sleep(0.08)

    def step(self, label: str):
        return _SpinnerStep(self, label)

    def _start(self, label: str):
        if not self.enabled:
            return
        self._label = label
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _finish(self, label: str, elapsed: float, ok: bool = True):
        if not self.enabled:
            return
        self._stop.set()
        if self._thread:
            self._thread.join()
        mark = c("✓", "green") if ok else c("✗", "red")
        took = c(f"{elapsed:.1f}s", "gray")
        sys.stderr.write(f"\r{mark} {c(label, 'dim')} {took}\033[K\n")
        sys.stderr.flush()


class _SpinnerStep:
    def __init__(self, spinner: Spinner, label: str):
        self.spinner = spinner
        self.label = label
        self.t0 = 0.0

    def __enter__(self):
        self.t0 = time.monotonic()
        self.spinner._start(self.label)
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed = time.monotonic() - self.t0
        self.spinner._finish(self.label, elapsed, ok=exc_type is None)
        return False


# ── 결과 렌더 ──────────────────────────────────────────────
def _abbrev_path(path: str) -> str:
    home = str(Path.home())
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


def _group_by_doc(rows: list[dict]) -> list[dict]:
    """같은 문서(path)의 여러 청크를 한 카드로 묶는다. 최고 점수 청크를 대표로."""
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in rows:
        key = (r["project"], r["path"])
        if key not in groups:
            groups[key] = {**r, "_chunks": 1}
            order.append(key)
        else:
            g = groups[key]
            g["_chunks"] += 1
            if r["score"] > g["score"]:
                g["score"], g["text"] = r["score"], r["text"]
    return [groups[k] for k in order]


def _score_bar(score: float, top: float, width: int = 10, enabled: bool = True) -> str:
    ratio = (score / top) if top > 0 else 0.0
    filled = max(1, round(ratio * width)) if score > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    return c(bar, "green", enabled=enabled)


def _highlight(text: str, query: str, enabled: bool) -> str:
    """쿼리 토큰을 본문에서 강조."""
    if not enabled or not query.strip():
        return text
    for tok in sorted(set(query.split()), key=len, reverse=True):
        if len(tok) < 2:
            continue
        low_text, low_tok = text.lower(), tok.lower()
        out, idx = [], 0
        while True:
            pos = low_text.find(low_tok, idx)
            if pos < 0:
                out.append(text[idx:])
                break
            out.append(text[idx:pos])
            out.append(c(text[pos:pos + len(tok)], "bgyellow"))
            idx = pos + len(tok)
        text, low_text = "".join(out), "".join(out).lower()
    return text


def _wrap(text: str, width: int, max_lines: int = 6) -> list[str]:
    """텍스트를 width 기준으로 word-wrap하여 최대 max_lines 줄 반환.

    원본 줄 구조(\\n)를 보존한다: 각 줄을 개별로 wrap하여 합친다.
    """
    if not text:
        return []
    raw_lines = text.split("\n")
    lines: list[str] = []
    for raw_line in raw_lines:
        if not raw_line.strip():
            lines.append("")
        else:
            wrapped = textwrap.wrap(raw_line, width=width) or [raw_line]
            lines.extend(wrapped)
        if len(lines) >= max_lines:
            break

    lines = lines[:max_lines]

    # 원본에 더 내용이 있으면 마지막 줄에 … 추가
    full_count = 0
    for raw_line in raw_lines:
        if not raw_line.strip():
            full_count += 1
        else:
            full_count += len(textwrap.wrap(raw_line, width=width) or [raw_line])

    if full_count > max_lines and lines:
        lines[-1] = lines[-1].rstrip() + " …"
    return lines


def _extract_excerpt(text: str, query: str, max_lines: int = 6, width: int = 80) -> list[str]:
    """쿼리 토큰이 포함된 줄을 앞으로, 나머지를 뒤에 붙여 max_lines 슬라이싱."""
    all_lines: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line.strip():
            all_lines.append("")
        else:
            wrapped = textwrap.wrap(raw_line, width=width) or [raw_line]
            all_lines.extend(wrapped)

    if not query.strip():
        return all_lines[:max_lines]

    tokens = [t.lower() for t in query.split() if len(t) >= 2]
    relevant: list[str] = []
    rest: list[str] = []
    for line in all_lines:
        line_lower = line.lower()
        if any(tok in line_lower for tok in tokens):
            relevant.append(line)
        else:
            rest.append(line)

    combined = relevant + rest
    result = combined[:max_lines]
    if len(combined) > max_lines and result:
        result[-1] = result[-1].rstrip() + " …"
    return result


def render_results(
    rows: list[dict],
    query: str,
    *,
    enabled: bool = True,
    context_chunks: dict | None = None,
) -> tuple[str, list[dict]]:
    """색상 멀티라인 카드 렌더. (출력문자열, 그룹화된_결과리스트) 반환."""
    grouped = _group_by_doc(rows)
    if not grouped:
        return c("결과 없음", "yellow", enabled=enabled), grouped
    term_w = shutil.get_terminal_size((100, 24)).columns
    body_w = max(40, min(term_w, 120) - 5)
    top = max(g["score"] for g in grouped)
    out = []
    for i, g in enumerate(grouped, 1):
        bar = _score_bar(g["score"], top, enabled=enabled)
        rank = c(f"{i:>2}", "bold", enabled=enabled)
        score = f"{g['score']:.4f}"
        proj = c(g["project"], "dim", enabled=enabled)
        chunks = c(f"·{g['_chunks']}청크", "gray", enabled=enabled) if g["_chunks"] > 1 else ""
        path_line = (
            "     "
            + c(Path(g["path"]).name, "bold", enabled=enabled)
            + "  "
            + c(_abbrev_path(g["path"]), "dim", enabled=enabled)
        )
        out.append("")
        out.append(f" {rank}  {bar} {score}  {proj} {chunks}")
        out.append(path_line)

        # 컨텍스트 청크 (앞) — dim 스타일
        if context_chunks is not None:
            ctx_key = (g["project"], g["path"])
            ctx = context_chunks.get(ctx_key, [])
            center_idx = g.get("chunk_index", 0)
            prev_chunks = [ci for ci in ctx if ci.get("chunk_index", 999) < center_idx]
            next_chunks = [ci for ci in ctx if ci.get("chunk_index", 0) > center_idx]
            for ctx_item in prev_chunks:
                for line in _wrap(ctx_item["text"], body_w, max_lines=2):
                    out.append("     " + c(line, "dim", enabled=enabled))
        else:
            next_chunks = []

        # 발췌 (relevance-first)
        excerpt_lines = _extract_excerpt(g["text"], query, max_lines=6, width=body_w)
        for line in excerpt_lines:
            out.append("     " + _highlight(line, query, enabled))

        # 컨텍스트 청크 (뒤) — dim 스타일
        if context_chunks is not None:
            for ctx_item in next_chunks:
                for line in _wrap(ctx_item["text"], body_w, max_lines=2):
                    out.append("     " + c(line, "dim", enabled=enabled))

    return "\n".join(out), grouped


def _preview(path: str) -> None:
    """bat 또는 less로 파일을 터미널에서 미리보기."""
    if shutil.which("bat"):
        subprocess.run(["bat", "--style=numbers", "--paging=always", path])
    else:
        subprocess.run(["less", "-N", path])


def open_path(path: str) -> tuple[bool, str]:
    """OS 기본 앱으로 파일을 연다."""
    if not Path(path).exists():
        return False, "파일이 경로에 없음(로테이션·이동 가능)"
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=True)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", path], check=True)
        else:
            return False, f"미지원 플랫폼: {sys.platform}"
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def open_fulltext_fallback(conn, project: str, source_path: str) -> tuple[bool, str]:
    """원본 파일이 없으면 DB full_text를 임시파일로 떨궈 연다."""
    cur = conn.cursor()
    cur.execute(
        "SELECT full_text FROM doc_originals WHERE project=%s AND source_path=%s",
        (project, source_path),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return False, "DB에 원문도 없음"
    tmp = Path("/tmp") / f"loregist_{Path(source_path).name}"
    tmp.write_text(row[0], encoding="utf-8")
    ok, msg = open_path(str(tmp))
    return ok, (msg or f"(DB 원문 복원 → {tmp})")


def prompt_open(grouped: list[dict], conn=None) -> None:
    """번호 입력받아 기본앱으로 연다. Enter/빈입력/EOF면 종료."""
    if not grouped:
        return
    enabled = color_enabled(sys.stdout)
    print()
    hint = f" ↳ 번호를 입력하면 기본 앱으로 엽니다 (1-{len(grouped)}, p<번호>=미리보기, Enter=종료)"
    print(hint)
    while True:
        try:
            raw = input(c("열기 ▸ ", "cyan", enabled=enabled)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not raw:
            return
        # p<숫자> 패턴: 미리보기 모드
        m = re.match(r"^p(\d+)$", raw)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(grouped):
                _preview(grouped[idx]["path"])
            else:
                print(c(f"  1~{len(grouped)} 범위 숫자를 입력하세요.", "yellow", enabled=enabled))
            continue
        if not raw.isdigit() or not (1 <= int(raw) <= len(grouped)):
            print(c(f"  1~{len(grouped)} 범위 숫자를 입력하세요.", "yellow", enabled=enabled))
            continue
        g = grouped[int(raw) - 1]
        ok, msg = open_path(g["path"])
        if not ok and conn is not None:
            ok, msg = open_fulltext_fallback(conn, g["project"], g["path"])
        if ok:
            print(c(f"  ✓ 열림: {Path(g['path']).name} {msg}", "green", enabled=enabled))
        else:
            print(c(f"  ✗ 열기 실패: {msg}", "red", enabled=enabled))
        # 루프 복귀 — Enter/EOF/KeyboardInterrupt 전까지 계속 입력받는다

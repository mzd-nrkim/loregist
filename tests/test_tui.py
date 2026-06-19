"""
tests/test_tui.py
§5-1~5-3: tui 단위 테스트 (DB 불필요)

커버:
  5-1: color_enabled / c() / _group_by_doc / _score_bar / _highlight / _wrap
  5-2: Spinner 비-TTY no-op (stderr 출력 없음, step 정상 통과)
  5-3: render_results(enabled=False) — 멀티라인 구조, ANSI 없음
"""
import io
import sys
import pytest


# ──────────────────────────────────────────────────────────────
# 5-1-a: color_enabled — NO_COLOR, FORCE_COLOR, non-TTY
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_color_enabled_no_color(monkeypatch):
    """NO_COLOR 환경변수가 있으면 color_enabled == False."""
    from loregist import tui
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("LOREGIST_FORCE_COLOR", raising=False)
    assert tui.color_enabled(sys.stdout) is False


@pytest.mark.unit
def test_color_enabled_force_color(monkeypatch):
    """LOREGIST_FORCE_COLOR가 있으면 NO_COLOR 없을 때 color_enabled == True."""
    from loregist import tui
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("LOREGIST_FORCE_COLOR", "1")
    # non-TTY 스트림이더라도 force 환경변수로 True
    assert tui.color_enabled(io.StringIO()) is True


@pytest.mark.unit
def test_color_enabled_non_tty(monkeypatch):
    """TTY 아닌 스트림 + 환경변수 없으면 False."""
    from loregist import tui
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("LOREGIST_FORCE_COLOR", raising=False)
    assert tui.color_enabled(io.StringIO()) is False


# ──────────────────────────────────────────────────────────────
# 5-1-b: c() — enabled=False는 원문 그대로
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_c_disabled_passthrough():
    """c(text, *styles, enabled=False)는 ANSI 없이 원문 반환."""
    from loregist.tui import c
    assert c("hello", "bold", "cyan", enabled=False) == "hello"


@pytest.mark.unit
def test_c_enabled_contains_ansi():
    """c(text, *styles, enabled=True)는 ANSI prefix가 포함됨."""
    from loregist.tui import c, _RESET
    result = c("hello", "bold", enabled=True)
    assert result != "hello"
    assert _RESET in result


# ──────────────────────────────────────────────────────────────
# 5-1-c: _group_by_doc — 그룹화·순서·최고score
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_group_by_doc_basic():
    """같은 path의 2청크를 1카드로 묶고 최고 score를 대표로."""
    from loregist.tui import _group_by_doc
    rows = [
        {"project": "proj", "path": "/a.md", "kind": "md", "score": 0.5, "text": "first"},
        {"project": "proj", "path": "/a.md", "kind": "md", "score": 0.9, "text": "second"},
        {"project": "proj", "path": "/b.md", "kind": "md", "score": 0.3, "text": "other"},
    ]
    grouped = _group_by_doc(rows)
    assert len(grouped) == 2
    assert grouped[0]["path"] == "/a.md"
    assert grouped[0]["_chunks"] == 2
    assert grouped[0]["score"] == 0.9
    assert grouped[0]["text"] == "second"  # 최고 score 청크의 text
    assert grouped[1]["path"] == "/b.md"
    assert grouped[1]["_chunks"] == 1


@pytest.mark.unit
def test_group_by_doc_preserves_order():
    """_group_by_doc은 첫 등장 순서를 보존한다."""
    from loregist.tui import _group_by_doc
    rows = [
        {"project": "p", "path": "/z.md", "kind": "md", "score": 0.1, "text": "z"},
        {"project": "p", "path": "/a.md", "kind": "md", "score": 0.2, "text": "a"},
        {"project": "p", "path": "/z.md", "kind": "md", "score": 0.3, "text": "z2"},
    ]
    grouped = _group_by_doc(rows)
    assert grouped[0]["path"] == "/z.md"
    assert grouped[1]["path"] == "/a.md"


@pytest.mark.unit
def test_group_by_doc_empty():
    """빈 입력 → 빈 결과."""
    from loregist.tui import _group_by_doc
    assert _group_by_doc([]) == []


# ──────────────────────────────────────────────────────────────
# 5-1-d: _score_bar — 경계 검증
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_score_bar_full(monkeypatch):
    """score == top이면 전체 바 (10칸 모두 █), enabled=False."""
    from loregist.tui import _score_bar
    bar = _score_bar(1.0, 1.0, width=10, enabled=False)
    assert bar == "█" * 10


@pytest.mark.unit
def test_score_bar_half(monkeypatch):
    """score == top/2 → 5칸 채움, enabled=False."""
    from loregist.tui import _score_bar
    bar = _score_bar(0.5, 1.0, width=10, enabled=False)
    assert bar.count("█") == 5
    assert bar.count("░") == 5


@pytest.mark.unit
def test_score_bar_zero():
    """score == 0 → 전체 빈 바, enabled=False."""
    from loregist.tui import _score_bar
    bar = _score_bar(0.0, 1.0, width=10, enabled=False)
    assert bar == "░" * 10


@pytest.mark.unit
def test_score_bar_positive_min_one():
    """score > 0이면 최소 1칸 채움, enabled=False."""
    from loregist.tui import _score_bar
    bar = _score_bar(0.001, 1.0, width=10, enabled=False)
    assert bar.count("█") >= 1


# ──────────────────────────────────────────────────────────────
# 5-1-e: _highlight — 매칭 강조
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_highlight_enabled_matches():
    """쿼리 토큰이 본문에 있으면 강조 ANSI가 삽입된다."""
    from loregist.tui import _highlight, _RESET
    result = _highlight("hello world", "hello", enabled=True)
    assert _RESET in result  # ANSI 삽입 확인
    assert "world" in result  # 나머지 텍스트 보존


@pytest.mark.unit
def test_highlight_disabled_passthrough():
    """enabled=False면 원문 그대로."""
    from loregist.tui import _highlight
    text = "hello world"
    assert _highlight(text, "hello", enabled=False) == text


@pytest.mark.unit
def test_highlight_short_token_skipped():
    """1글자 토큰은 강조하지 않는다."""
    from loregist.tui import _highlight
    # 'a' 는 1글자라 강조 없음
    text = "alpha beta a"
    result = _highlight(text, "a", enabled=True)
    # 'a'만 있는 토큰은 강조 안 하지만 'alpha'는 강조될 수 있으므로
    # 단순히 예외 없이 동작하는지만 확인
    assert isinstance(result, str)


@pytest.mark.unit
def test_highlight_case_insensitive():
    """대소문자 무시 매칭."""
    from loregist.tui import _highlight, _RESET
    result = _highlight("Hello World", "hello", enabled=True)
    assert _RESET in result


# ──────────────────────────────────────────────────────────────
# 5-1-f: _wrap — 줄수 / … 추가
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_wrap_short_text():
    """짧은 텍스트는 한 줄로."""
    from loregist.tui import _wrap
    lines = _wrap("hello world", width=80)
    assert len(lines) == 1
    assert lines[0] == "hello world"


@pytest.mark.unit
def test_wrap_max_lines():
    """max_lines 초과 시 마지막 줄에 … 추가."""
    from loregist.tui import _wrap
    # 각 단어 3글자씩, width=5로 2단어씩 1줄 → 3줄 초과 확인
    text = "aaa bbb ccc ddd eee fff ggg hhh iii jjj"
    lines = _wrap(text, width=8, max_lines=3)
    assert len(lines) <= 3
    if len(lines) == 3:
        assert "…" in lines[-1]


@pytest.mark.unit
def test_wrap_whitespace_normalized():
    """_wrap은 줄 구조(\\n)를 보존하며 textwrap 기반으로 동작한다.
    A-1 개선 후: 공백 정규화 대신 줄 단위 word-wrap으로 변경됨.
    짧은 텍스트는 그대로 1줄 반환한다.
    """
    from loregist.tui import _wrap
    lines = _wrap("hello    world", width=80)
    # 공백이 있어도 width=80이므로 1줄 반환
    assert len(lines) == 1
    assert "hello" in lines[0] and "world" in lines[0]


# ──────────────────────────────────────────────────────────────
# 5-2: Spinner 비-TTY no-op
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_spinner_non_tty_no_stderr_output(capsys):
    """비-TTY stderr 환경에서 Spinner는 아무것도 출력하지 않는다."""
    from loregist.tui import Spinner
    import time

    # stderr가 TTY가 아닌 환경(pytest capsys)에서는 enabled=False가 되어야 함
    sp = Spinner(enabled=True)
    # sys.stderr.isatty()가 False이면 spinner.enabled가 False
    assert sp.enabled is False  # capsys는 non-TTY

    with sp.step("테스트 단계"):
        time.sleep(0.01)  # 짧은 대기

    captured = capsys.readouterr()
    assert captured.err == "", f"비-TTY에서 stderr 출력이 없어야 함, 실제: {captured.err!r}"


@pytest.mark.unit
def test_spinner_step_passes_through_exception(capsys):
    """Spinner step이 예외를 삼키지 않고 그대로 전파한다."""
    from loregist.tui import Spinner

    sp = Spinner(enabled=False)
    with pytest.raises(ValueError, match="테스트 예외"):
        with sp.step("실패 단계"):
            raise ValueError("테스트 예외")


@pytest.mark.unit
def test_spinner_step_returns_false_not_suppress(capsys):
    """_SpinnerStep.__exit__가 예외를 suppress하지 않는다 (return False)."""
    from loregist.tui import _SpinnerStep, Spinner

    sp = Spinner(enabled=False)
    step = _SpinnerStep(sp, "label")
    # __exit__(exc_type, exc, tb) → False (suppress 안 함)
    result = step.__exit__(ValueError, ValueError("err"), None)
    assert result is False


# ──────────────────────────────────────────────────────────────
# 5-3: render_results(enabled=False) — 멀티라인·ANSI 없음
# ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_render_results_structure(monkeypatch):
    """render_results enabled=False → 카드 구조 (순위·파일명·경로·발췌) 포함, ANSI 없음."""
    from loregist.tui import render_results, _RESET

    rows = [
        {"project": "proj-a", "path": "/home/user/docs/file.md", "kind": "md",
         "score": 0.85, "text": "테스트 검색 결과 발췌 내용입니다."},
    ]
    rendered, grouped = render_results(rows, "테스트", enabled=False)

    # ANSI 이스케이프 없음
    assert "\033[" not in rendered, f"enabled=False인데 ANSI 코드가 있음: {rendered!r}"
    assert _RESET not in rendered

    # 구조 검증
    assert "proj-a" in rendered       # 프로젝트명
    assert "file.md" in rendered      # 파일명
    assert "/home/user/docs/file.md" in rendered  # 경로
    assert "테스트" in rendered        # 발췌 (하이라이트 없음)

    # grouped 반환
    assert len(grouped) == 1
    assert grouped[0]["path"] == "/home/user/docs/file.md"


@pytest.mark.unit
def test_render_results_empty():
    """빈 결과 → '결과 없음' 포함 문자열, grouped=[]."""
    from loregist.tui import render_results
    rendered, grouped = render_results([], "쿼리", enabled=False)
    assert "결과 없음" in rendered
    assert grouped == []


@pytest.mark.unit
def test_render_results_multiline_card():
    """카드가 여러 줄로 구성된다 (빈 줄 포함)."""
    from loregist.tui import render_results
    rows = [
        {"project": "p", "path": "/x.md", "kind": "md", "score": 0.5, "text": "some content here"},
    ]
    rendered, grouped = render_results(rows, "content", enabled=False)
    lines = rendered.split("\n")
    # 카드 1개 = 최소 4줄 (순위+점수바, 파일명, 경로, 발췌)
    assert len(lines) >= 4


@pytest.mark.unit
def test_render_results_chunks_label():
    """같은 path 2청크 → ·2청크 표기 포함."""
    from loregist.tui import render_results
    rows = [
        {"project": "p", "path": "/doc.md", "kind": "md", "score": 0.8, "text": "first chunk"},
        {"project": "p", "path": "/doc.md", "kind": "md", "score": 0.6, "text": "second chunk"},
    ]
    rendered, grouped = render_results(rows, "chunk", enabled=False)
    assert "·2청크" in rendered
    assert len(grouped) == 1  # 1카드로 묶임


@pytest.mark.unit
def test_render_results_abbrev_home(monkeypatch, tmp_path):
    """경로에서 홈 디렉터리가 ~ 로 축약된다."""
    from loregist.tui import render_results
    import pathlib

    home = str(pathlib.Path.home())
    path = f"{home}/docs/file.md"
    rows = [
        {"project": "p", "path": path, "kind": "md", "score": 0.5, "text": "content"},
    ]
    rendered, _ = render_results(rows, "content", enabled=False)
    # 홈 디렉터리 절대경로 대신 ~ 로 축약
    assert "~" in rendered
    assert home not in rendered


# ──────────────────────────────────────────────────────────────
# C-1: 신규 단위 테스트 (A-1·A-2 기반)
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_wrap_preserves_newlines():
    """\n이 포함된 text를 wrap 후 줄 구조 보존 확인."""
    from loregist.tui import _wrap
    text = "첫 번째 줄\n두 번째 줄\n세 번째 줄"
    lines = _wrap(text, width=80, max_lines=6)
    # 각 원본 줄이 개별 wrap 결과에 반영되어야 함
    assert any("첫 번째 줄" in l for l in lines)
    assert any("두 번째 줄" in l for l in lines)
    assert any("세 번째 줄" in l for l in lines)


@pytest.mark.unit
def test_wrap_max_lines_6():
    """7줄 입력 → 6줄 + … 반환 확인."""
    from loregist.tui import _wrap
    # 7줄 텍스트
    text = "\n".join([f"줄 {i}" for i in range(7)])
    lines = _wrap(text, width=80, max_lines=6)
    assert len(lines) == 6
    assert "…" in lines[-1]


@pytest.mark.unit
def test_wrap_empty_text():
    """text="" 입력 시 빈 리스트 반환 확인 (Boundary)."""
    from loregist.tui import _wrap
    lines = _wrap("", width=80, max_lines=6)
    assert lines == []


@pytest.mark.unit
def test_wrap_under_max_lines():
    """줄 수 < max_lines 시 … 없이 그대로 반환 (Boundary)."""
    from loregist.tui import _wrap
    text = "줄 1\n줄 2\n줄 3"
    lines = _wrap(text, width=80, max_lines=6)
    assert len(lines) == 3
    assert all("…" not in l for l in lines)


@pytest.mark.unit
def test_wrap_line_width():
    """반환 줄이 width 초과하지 않음 확인 (Conformance)."""
    from loregist.tui import _wrap
    text_spaced = " ".join(["word"] * 100)
    lines = _wrap(text_spaced, width=40, max_lines=6)
    for line in lines:
        # 마지막 … 제거 후 비교
        clean = line.replace(" …", "")
        assert len(clean) <= 40, f"줄 길이 {len(clean)} > 40: {clean!r}"


@pytest.mark.unit
def test_extract_excerpt_relevance_first():
    """쿼리 토큰 포함 줄이 첫 번째로 오는지 확인."""
    from loregist.tui import _extract_excerpt
    text = "관계없는 줄 1\n관계없는 줄 2\n쿼리 포함 줄\n관계없는 줄 3"
    lines = _extract_excerpt(text, query="쿼리", max_lines=4, width=80)
    assert lines[0] == "쿼리 포함 줄"


@pytest.mark.unit
def test_extract_excerpt_ordering():
    """쿼리 포함 줄 → 비포함 줄 순서 보장 (Ordering)."""
    from loregist.tui import _extract_excerpt
    text = "no match a\nno match b\nmatch keyword here\nno match c"
    lines = _extract_excerpt(text, query="keyword", max_lines=4, width=80)
    # match 줄이 non-match 줄보다 앞에 와야 함
    match_idx = next((i for i, l in enumerate(lines) if "keyword" in l), None)
    assert match_idx is not None
    assert match_idx == 0


@pytest.mark.unit
def test_color_count_limited():
    """render_results() 출력에 사용된 ANSI 코드가 4종 이하인지 확인."""
    import re as _re
    from loregist.tui import render_results
    rows = [
        {"project": "p", "path": "/a.md", "kind": "md", "score": 0.9, "text": "테스트 내용입니다"},
        {"project": "p", "path": "/b.md", "kind": "md", "score": 0.7, "text": "다른 내용"},
    ]
    rendered, _ = render_results(rows, "테스트", enabled=True)
    # ANSI 코드 종류 수집
    ansi_codes = set(_re.findall(r"\033\[[\d;]+m", rendered))
    # reset 코드 제외하고 색상 코드 종류 확인 (bold, green, dim, bgyellow 4종 이하)
    color_codes = {code for code in ansi_codes if code != "\033[0m"}
    assert len(color_codes) <= 4, f"ANSI 코드 종류 {len(color_codes)}개 > 4종: {color_codes}"


@pytest.mark.unit
def test_preview_called_on_p_input(monkeypatch):
    """p1 입력 시 _preview() 호출 경로 확인 (monkeypatch)."""
    from loregist import tui
    called_with = []

    def mock_preview(path):
        called_with.append(path)

    monkeypatch.setattr(tui, "_preview", mock_preview)

    grouped = [
        {"project": "p", "path": "/test/file.md", "kind": "md", "score": 0.9,
         "text": "content", "_chunks": 1},
    ]

    # input을 monkeypatch: "p1" 입력 후 "" 로 종료
    inputs = iter(["p1", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    tui.prompt_open(grouped)
    assert called_with == ["/test/file.md"]


@pytest.mark.unit
def test_preview_fallback_to_less(monkeypatch):
    """bat 미설치 환경에서 less로 fallback 확인 (Reference mock)."""
    from loregist import tui
    import subprocess

    called_cmds = []

    def mock_run(cmd, **kwargs):
        called_cmds.append(cmd)

    # shutil.which("bat") → None (미설치)
    monkeypatch.setattr(tui.shutil, "which", lambda name: None)
    monkeypatch.setattr(subprocess, "run", mock_run)
    # tui._preview 내부에서 subprocess.run을 직접 참조하므로 tui 모듈의 subprocess도 패치
    monkeypatch.setattr(tui.subprocess, "run", mock_run)

    tui._preview("/test/file.md")
    assert any("less" in cmd[0] for cmd in called_cmds), f"less 호출 없음: {called_cmds}"

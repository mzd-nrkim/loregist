"""
tests/test_onboard_int.py
G-3: project add 온보딩 통합 테스트 — 실 pgvector DB 사용

DB 미기동 시 conftest.pytest_collection_modifyitems가 @pytest.mark.integration 테스트를 자동 skip.
teardown: 임시 toml/디렉터리는 tmp_path가 자동 정리, DB 행은 fixture finalizer로 정리.
테스트 프로젝트 키: tc_onboard_proj (충돌 없는 고유값)
"""
from __future__ import annotations

from pathlib import Path

import pytest

_TC_PROJECT = "tc-onboard-proj"


# ──────────────────────────────────────────────────────────────
# DB teardown 헬퍼
# ──────────────────────────────────────────────────────────────

def _cleanup_db(project_key: str) -> None:
    """doc_chunks → doc_originals 순으로 테스트 행 삭제."""
    from loregist.config import get_db_connection
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM doc_chunks WHERE project = %s",
                (project_key,),
            )
            cur.execute(
                "DELETE FROM doc_originals WHERE project = %s",
                (project_key,),
            )
        conn.commit()


# ──────────────────────────────────────────────────────────────
# G-3: project add → embed → DB 행 생성 확인
# ──────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_project_add_embed_creates_db_rows(tmp_path, monkeypatch):
    """
    G-3 / Right + DB 통합:
    project add (비대화 플래그, --yes) → embed 수행 → 실 DB의
    doc_originals에 해당 project 행 ≥1, doc_chunks에 대응 청크 행 생성 확인.

    teardown: tmp_path 자동 정리(toml/디렉터리), DB 행은 finally로 정리.
    """
    import os
    import sys
    import loregist.config as config_mod
    import loregist.embed as embed_mod

    project_key = _TC_PROJECT

    # ── 사전 정리: 이전 테스트 잔여물 제거 ─────────────────────
    try:
        _cleanup_db(project_key)
    except Exception:
        pass  # DB 미기동 시 skip되므로 여기까지 오면 연결 가능

    # ── 임시 환경 구성 ─────────────────────────────────────────
    # 1) 임시 WORKSPACE
    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()

    # 2) vault 아래 .log 파일 미리 생성 (embed 대상 — vault/*.log는 날짜 제외 없이 무조건 스캔)
    #    onboard가 `--vault logvault/tc-onboard-proj`를 받아 WORKSPACE/logvault/tc-onboard-proj를
    #    _create_dirs(exist_ok=True)로 만들므로, 미리 생성한 파일이 제거되지 않는다.
    vault_dir = fake_workspace / "logvault" / project_key
    vault_dir.mkdir(parents=True, exist_ok=True)
    sample_log = vault_dir / "sample.log"
    sample_log.write_text(
        "## 온보딩 통합 테스트 로그\n"
        + ("이 파일은 project add 통합 테스트용 vault 로그입니다. " * 6),
        encoding="utf-8",
    )

    # 3) 임시 projects.toml (초기: 비어 있음)
    toml_path = tmp_path / "projects.toml"
    toml_path.write_text("", encoding="utf-8")

    # ── monkeypatch: config 모듈의 전역 변수 격리 ──────────────
    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)

    # embed 모듈이 참조하는 WORKSPACE / LOGVAULT_DIR도 패치
    monkeypatch.setattr(embed_mod, "LOGVAULT_DIR", tmp_path / "logvault")
    (tmp_path / "logvault").mkdir()

    # ── project add 실행 (비대화, --yes) ────────────────────────
    import os as _os
    # stdin 비-TTY 패치
    monkeypatch.setattr("sys.stdin", open(_os.devnull))

    from loregist.onboard import main as onboard_main

    # _run_embed은 실제 DB에 쓰므로 직접 실행 허용.
    # 단, subprocess.run([sys.executable, "-m", "loregist.embed", ...])는 별도 프로세스 — PROJECTS_FILE 패치가
    # 서브프로세스에 전달되지 않으므로, _run_embed를 monkeypatch로 대체해 동일 프로세스 내에서 embed.main() 호출.
    def _inline_embed(key: str) -> int:
        """embed를 동일 프로세스 내에서 실행해 monkeypatch PROJECTS 패치 적용."""
        # embed.main()은 sys.argv를 참조하므로 임시 argv 설정
        old_argv = sys.argv[:]
        sys.argv = ["loregist.embed", "--project", key]
        try:
            # PROJECTS를 최신 toml 기준으로 재로드하여 embed에 반영
            projects = config_mod.load_projects(toml_path)
            monkeypatch.setattr(config_mod, "PROJECTS", projects)
            monkeypatch.setattr(embed_mod, "PROJECTS", projects)
            embed_mod.main()
            return 0
        except SystemExit as e:
            return int(e.code) if e.code is not None else 0
        except Exception:
            return 1
        finally:
            sys.argv = old_argv

    import loregist.onboard as onboard_mod
    monkeypatch.setattr(onboard_mod, "_run_embed", _inline_embed)
    # catalog 사용 안 함 — _run_catalog_init는 호출 안 됨
    monkeypatch.setattr(onboard_mod, "_run_catalog_init", lambda key: 0)

    try:
        rc = onboard_main([
            "--project", project_key,
            "--type", "docs_root",
            "--docs-root", f"tc-onboard-proj/dev",
            "--vault", f"logvault/{project_key}",
            "--cold", f"logvault/{project_key}/cold",
            "--no-catalog",
            "--yes",
        ])
        # 성공(0) 또는 embed 일부 실패(2) 모두 허용 — 여기서는 DB 행 생성만 검증
        assert rc in (0, 2), (
            f"project add 결과 코드가 0 또는 2여야 함 (0=성공, 2=embed 실패), 실제: {rc}"
        )

        # ── DB 행 검증 ────────────────────────────────────────────
        from loregist.config import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM doc_originals WHERE project = %s",
                    (project_key,),
                )
                orig_count = cur.fetchone()[0]

            assert orig_count >= 1, (
                f"doc_originals에 project='{project_key}' 행이 ≥1이어야 함, 실제: {orig_count}"
            )

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM doc_chunks WHERE project = %s",
                    (project_key,),
                )
                chunk_count = cur.fetchone()[0]

            assert chunk_count >= 1, (
                f"doc_chunks에 project='{project_key}' 대응 청크가 ≥1이어야 함, 실제: {chunk_count}"
            )

    finally:
        # ── DB teardown ───────────────────────────────────────────
        try:
            _cleanup_db(project_key)
        except Exception:
            pass  # teardown 실패는 무시 (다음 실행 전 cleanup이 사전 정리)


@pytest.mark.integration
def test_project_add_toml_block_written(tmp_path, monkeypatch):
    """
    G-3 / Right + Inverse:
    project add 후 projects.toml에 해당 키 블록이 추가되고,
    tomllib으로 재파싱했을 때 키가 존재함을 확인.
    (embed는 mock — TOML 쓰기 단계만 검증)
    """
    import os
    import sys
    import tomllib
    import loregist.config as config_mod
    import loregist.onboard as onboard_mod

    project_key = "tc-toml-write"

    # 임시 환경 구성
    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()
    docs_dev = fake_workspace / project_key / "dev"
    docs_dev.mkdir(parents=True)

    toml_path = tmp_path / "projects.toml"
    toml_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)
    monkeypatch.setattr("sys.stdin", open(os.devnull))

    # embed와 catalog는 mock
    monkeypatch.setattr(onboard_mod, "_run_embed", lambda key: 0)
    monkeypatch.setattr(onboard_mod, "_run_catalog_init", lambda key: 0)

    from loregist.onboard import main as onboard_main

    try:
        rc = onboard_main([
            "--project", project_key,
            "--type", "docs_root",
            "--docs-root", f"{project_key}/dev",
            "--vault", f"logvault/{project_key}",
            "--cold", f"logvault/{project_key}/cold",
            "--no-catalog",
            "--yes",
        ])

        # TOML 파일에 블록이 추가되었는지 확인
        content = toml_path.read_text(encoding="utf-8")
        assert f"[projects.{project_key}]" in content, (
            f"projects.toml에 '[projects.{project_key}]' 블록이 있어야 함.\n내용:\n{content}"
        )

        # tomllib 재파싱
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        assert project_key in data.get("projects", {}), (
            f"tomllib 재파싱 시 '{project_key}'가 projects에 있어야 함"
        )

    finally:
        # 이 테스트는 DB에 쓰지 않으므로 DB teardown 불필요
        pass


@pytest.mark.integration
def test_project_add_creates_directories(tmp_path, monkeypatch):
    """
    G-3 / Existence:
    project add 후 docs_root / vault / cold 디렉터리가 생성되어 있어야 함.
    (embed는 mock)
    """
    import os
    import loregist.config as config_mod
    import loregist.onboard as onboard_mod

    project_key = "tc-dirs-proj"

    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()

    toml_path = tmp_path / "projects.toml"
    toml_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(config_mod, "PROJECTS_FILE", toml_path)
    monkeypatch.setattr(config_mod, "WORKSPACE", fake_workspace)
    monkeypatch.setattr("sys.stdin", open(os.devnull))
    monkeypatch.setattr(onboard_mod, "_run_embed", lambda key: 0)
    monkeypatch.setattr(onboard_mod, "_run_catalog_init", lambda key: 0)

    from loregist.onboard import main as onboard_main

    rc = onboard_main([
        "--project", project_key,
        "--type", "docs_root",
        "--docs-root", f"{project_key}/dev",
        "--vault", f"logvault/{project_key}",
        "--cold", f"logvault/{project_key}/cold",
        "--no-catalog",
        "--yes",
    ])

    # docs_root 경로 (WORKSPACE 기준)
    docs_root_path = fake_workspace / project_key / "dev"
    vault_path = fake_workspace / "logvault" / project_key
    cold_path = fake_workspace / "logvault" / project_key / "cold"

    assert docs_root_path.exists(), f"docs_root 디렉터리가 생성되어야 함: {docs_root_path}"
    assert vault_path.exists(), f"vault 디렉터리가 생성되어야 함: {vault_path}"
    assert cold_path.exists(), f"cold 디렉터리가 생성되어야 함: {cold_path}"

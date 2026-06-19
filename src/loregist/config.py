import json as _json
import os
import sys
import contextlib
from pathlib import Path
import psycopg2
import tomllib

DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "loregist",
    "user": "loregist",
    "password": os.environ.get("LOREGIST_DB_PASSWORD", "vector_local"),
}

MODEL_NAME = "dragonkue/multilingual-e5-small-ko-v2"
EMBED_DIM = 384

ROTATE_TO_VAULT_DAYS = 7

# vault 정리 기본 보존 기간(일). 프로젝트가 vault_cleanup=<정수>로 override 가능.
# vault_cleanup=true 지정 시 이 값이 사용되며, vault_cleanup=<정수>이면 해당 값으로 override.
VAULT_RETENTION_DAYS = 90

MODELS_DIR = Path(__file__).parent.parent.parent / "models"

WORKSPACE = Path(os.environ.get("LOREGIST_WORKSPACE", str(Path.home() / "workspace")))

PROJECTS_FILE = Path(__file__).parent.parent.parent / "projects.toml"

def _resolve_path(p):
    """상대경로는 WORKSPACE 기준, 절대/~는 그대로, None/빈값은 None."""
    if not p:
        return None
    pp = Path(p).expanduser()
    return pp if pp.is_absolute() else WORKSPACE / p


def _parse_catalog(entry: dict, name: str) -> "Path | None":
    """
    projects.toml 단일 블록에서 catalog 키를 해석한다.

    - catalog = true  → {docs_root}/_catalog (docs_root 없으면 경고 + None)
    - catalog = "경로" → _resolve_path(경로)
    - 키 없음         → None (기본 off)
    """
    raw = entry.get("catalog")
    if raw is None:
        return None
    if isinstance(raw, bool):
        if not raw:
            return None
        docs_root_raw = entry.get("docs_root")
        if not docs_root_raw:
            print(
                f"[WARN] projects.{name}: catalog=true 이지만 docs_root가 없습니다 → catalog=None",
                file=sys.stderr,
            )
            return None
        return _resolve_path(docs_root_raw) / "_catalog"
    # 문자열 경로
    return _resolve_path(str(raw))


def _parse_vault_cleanup(entry: dict, name: str) -> "tuple[bool, int]":
    """
    projects.toml 단일 블록에서 vault_cleanup 키를 해석한다.

    반환: (활성 여부, 보존일)
    - vault_cleanup = true  → (True, VAULT_RETENTION_DAYS)
    - vault_cleanup = <int> → (True, <int>)
    - 키 없음               → (False, 0)
    """
    raw = entry.get("vault_cleanup")
    if raw is None:
        return (False, 0)
    if isinstance(raw, bool):
        return (raw, VAULT_RETENTION_DAYS if raw else 0)
    if isinstance(raw, int):
        return (True, raw)
    print(
        f"[WARN] projects.{name}: vault_cleanup 값이 bool 또는 정수가 아닙니다 ({raw!r}) → 비활성",
        file=sys.stderr,
    )
    return (False, 0)


def load_projects(path=PROJECTS_FILE):
    if not path.exists():
        raise FileNotFoundError(f"projects.toml 없음: {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    result = {}
    for name, e in data.get("projects", {}).items():
        vault_active, vault_retention = _parse_vault_cleanup(e, name)
        result[name] = {
            "vault": _resolve_path(e.get("vault")),
            "cold": _resolve_path(e.get("cold")),
            "done": _resolve_path(e.get("done")),
            "docs_root": _resolve_path(e.get("docs_root")),
            # catalog opt-in: None = 비대상, Path = 대상 경로
            "catalog": _parse_catalog(e, name),
            # vault_cleanup opt-in: {"active": bool, "retention_days": int}
            "vault_cleanup": {
                "active": vault_active,
                "retention_days": vault_retention if vault_active else None,
            },
        }
    return result

try:
    PROJECTS = load_projects()
except FileNotFoundError as e:
    example = PROJECTS_FILE.parent / "projects.toml.example"
    print(f"[ERROR] projects.toml 로드 실패: {e}", file=sys.stderr)
    if example.exists():
        print(
            f"[HINT]  초기 설정: cp {example} {PROJECTS_FILE}  후 경로를 수정하세요.",
            file=sys.stderr,
        )
    sys.exit(1)


def infer_project(cwd: str | None = None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    cwd = Path(cwd) if cwd else Path(os.environ.get("LOREGIST_CWD", str(Path.cwd())))
    # docs_root 및 docs_root.parent 기반 longest-match
    # docs_root 아래에 cwd가 있으면 docs_root.parts로, docs_root.parent 아래에 cwd가 있으면
    # docs_root.parent.parts로 비교 → 더 구체적인 프로젝트를 우선 반환
    best_match = None
    best_len = 0
    for key, cfg in PROJECTS.items():
        docs_root = cfg.get("docs_root")
        if docs_root is None:
            continue
        try:
            cwd.relative_to(docs_root)
            if len(docs_root.parts) > best_len:
                best_match = key
                best_len = len(docs_root.parts)
        except ValueError:
            try:
                cwd.relative_to(docs_root.parent)
                if len(docs_root.parent.parts) > best_len:
                    best_match = key
                    best_len = len(docs_root.parent.parts)
            except ValueError:
                pass
    if best_match:
        return best_match
    # fallback: cwd 경로 구성 요소에 프로젝트 키가 포함되면 반환
    for part in cwd.parts:
        if part in PROJECTS:
            return part
    # fallback: WORKSPACE 기준 첫 세그먼트
    try:
        rel = cwd.relative_to(WORKSPACE)
        candidate = rel.parts[0]
        if candidate in PROJECTS:
            return candidate
    except ValueError:
        pass
    raise ValueError(f"프로젝트를 추론할 수 없습니다 (cwd={cwd}). --project 를 사용하세요.")


@contextlib.contextmanager
def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError as e:
        raise psycopg2.OperationalError(
            f"pgvector DB 연결 실패 (host={DB_CONFIG['host']}, port={DB_CONFIG['port']}): {e}"
        ) from e
    try:
        yield conn
    finally:
        conn.close()


def dump_projects(as_json: bool = True) -> str:
    result = []
    for name, cfg in PROJECTS.items():
        vc = cfg.get("vault_cleanup", {})
        result.append({
            "name": name,
            "docs_root": str(cfg["docs_root"]) if cfg.get("docs_root") else None,
            "vault": str(cfg["vault"]) if cfg.get("vault") else None,
            "cold": str(cfg["cold"]) if cfg.get("cold") else None,
            "done": str(cfg["done"]) if cfg.get("done") else None,
            "catalog": str(cfg["catalog"]) if cfg.get("catalog") else None,
            "vault_cleanup": {
                "active": vc.get("active", False),
                "retention_days": vc.get("retention_days"),
            },
        })
    return _json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    project = infer_project()
    print(f"현재 프로젝트: {project}")
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT version()")
        print(f"DB 연결 OK: {cur.fetchone()[0][:40]}")

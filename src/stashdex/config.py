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
    "dbname": "stashdex",
    "user": "stashdex",
    "password": os.environ.get("STASHDEX_DB_PASSWORD", "vector_local"),
}

MODEL_NAME = "dragonkue/multilingual-e5-small-ko-v2"
EMBED_DIM = 384

ROTATE_TO_VAULT_DAYS = 7

# vault 정리 기본 보존 기간(일). 프로젝트가 vault_cleanup=<정수>로 override 가능.
# vault_cleanup=true 지정 시 이 값이 사용되며, vault_cleanup=<정수>이면 해당 값으로 override.
VAULT_RETENTION_DAYS = 90

# embed/watch/vault-cleanup/rotate 대상 확장자 기본값. projects.toml의 extensions 키로 프로젝트별 override 가능.
DEFAULT_EXTENSIONS: list[str] = ["md", "log", "txt"]

MODELS_DIR = Path(__file__).parent.parent.parent / "models"

WORKSPACE = Path(os.environ.get("STASHDEX_WORKSPACE", str(Path.home() / "workspace")))

PROJECTS_FILE = Path(
    os.environ.get("STASHDEX_PROJECTS_FILE", "")
) if os.environ.get("STASHDEX_PROJECTS_FILE") else (
    Path(__file__).parent.parent.parent / "projects.toml"
)

def _resolve_path(p):
    """상대경로는 WORKSPACE 기준, 절대/~는 그대로, None/빈값은 None."""
    if not p:
        return None
    pp = Path(p).expanduser()
    return pp if pp.is_absolute() else WORKSPACE / p


def _parse_catalog(entry: dict, name: str) -> "Path | None":
    """
    projects.toml 단일 블록에서 catalog 키를 해석한다.

    - catalog = true  → {docs_root}/_wiki (docs_root 없으면 경고 + None)
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
        return _resolve_path(docs_root_raw) / "_wiki"
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


def _parse_hot_days(entry: dict, name: str) -> int:
    """
    projects.toml 단일 블록에서 hot_days 키를 해석한다.

    반환: int (hot 보관 일수)
    - 키 없음(None)       → ROTATE_TO_VAULT_DAYS (전역 기본값)
    - bool              → WARN + ROTATE_TO_VAULT_DAYS (bool은 유효 입력 아님)
    - 양의 정수           → 해당 값
    - 0·음수·기타(문자열 등) → WARN + ROTATE_TO_VAULT_DAYS
    """
    raw = entry.get("hot_days")
    if raw is None:
        return ROTATE_TO_VAULT_DAYS
    # bool은 int 서브클래스이므로 isinstance(raw, int) 보다 먼저 체크
    if isinstance(raw, bool):
        print(
            f"[WARN] projects.{name}: hot_days에 bool 값이 지정되었습니다 ({raw!r}) → 기본값 {ROTATE_TO_VAULT_DAYS} 사용",
            file=sys.stderr,
        )
        return ROTATE_TO_VAULT_DAYS
    if isinstance(raw, int) and raw > 0:
        return raw
    print(
        f"[WARN] projects.{name}: hot_days 값이 양의 정수가 아닙니다 ({raw!r}) → 기본값 {ROTATE_TO_VAULT_DAYS} 사용",
        file=sys.stderr,
    )
    return ROTATE_TO_VAULT_DAYS


def _parse_handbook(entry: dict, name: str) -> "list[dict]":
    """
    projects.toml 단일 블록에서 handbook 키를 해석한다.

    반환: list[dict] — 각 항목은 {"path": Path, "writable": bool, "update_when": str | None}

    - 미선언(빈 값) → 빈 리스트
    - 문자열 항목 → {"path": _resolve_path(item), "writable": False, "update_when": None} (하위 호환)
    - dict(inline table) 항목 → path/writable/update_when 키 추출;
        path 키 누락 시 경고 후 스킵
    - 문자열/dict가 아닌 항목 → 경고 후 스킵
    - glob 패턴(*/**) 포함 시 WORKSPACE 기준으로 확장; 0건이면 경고
        확장된 각 경로에 동일 writable/update_when 메타 적용
    - 폴더 경로(is_dir()) 시 rglob("*.md")로 자동 확장; 0건이면 경고; 동일 writable/update_when 상속
    """
    raw_list = entry.get("handbook")
    if raw_list is None:
        return []
    result: list[dict] = []
    for item in raw_list:
        if isinstance(item, str):
            path_str = item
            writable = False
            update_when = None
        elif isinstance(item, dict):
            if "path" not in item:
                print(
                    f"[WARN] projects.{name}: handbook 항목에 'path' 키가 없습니다 ({item!r}) → 스킵",
                    file=sys.stderr,
                )
                continue
            path_str = str(item["path"])
            writable = bool(item.get("writable", False))
            update_when_raw = item.get("update_when")
            update_when = str(update_when_raw) if update_when_raw is not None else None
        else:
            print(
                f"[WARN] projects.{name}: handbook 항목이 문자열 또는 dict가 아닙니다 ({item!r}) → 스킵",
                file=sys.stderr,
            )
            continue

        if "*" in path_str or "**" in path_str:
            matched = sorted(WORKSPACE.glob(path_str))
            if not matched:
                print(
                    f"[WARN] projects.{name}: handbook 글로브 패턴 '{path_str}' 이 0건 매칭 — 무시합니다",
                    file=sys.stderr,
                )
            for p in matched:
                result.append({"path": p, "writable": writable, "update_when": update_when})
        else:
            resolved = _resolve_path(path_str)
            if resolved.is_dir():
                matched = sorted(resolved.rglob("*.md"))
                if not matched:
                    print(
                        f"[WARN] projects.{name}: handbook 폴더 '{path_str}' 내 .md 파일이 0건 — 무시합니다",
                        file=sys.stderr,
                    )
                for p in matched:
                    result.append({"path": p, "writable": writable, "update_when": update_when})
            else:
                result.append({"path": resolved, "writable": writable, "update_when": update_when})
    return result


def _parse_bool_flag(entry: dict, key: str, name: str) -> bool:
    """
    projects.toml 단일 블록에서 bool 플래그 키를 해석한다.

    - 키 없음(None) → False
    - bool          → 그 값
    - 그 외 타입    → [WARN] 출력 후 False
    """
    raw = entry.get(key)
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    print(
        f"[WARN] projects.{name}: {key} 값이 bool이 아닙니다 ({raw!r}) → False 사용",
        file=sys.stderr,
    )
    return False


def _parse_extensions(entry: dict, name: str) -> list[str]:
    """
    projects.toml 단일 블록에서 extensions 키를 해석한다.

    - extensions = ["md", "log", "txt"] → 지정 목록 사용 (dot 없이 저장)
    - 키 없음                           → DEFAULT_EXTENSIONS 반환
    - 리스트가 아닌 값                  → 경고 후 DEFAULT_EXTENSIONS 반환
    """
    raw = entry.get("extensions")
    if raw is None:
        return DEFAULT_EXTENSIONS[:]
    if isinstance(raw, list):
        cleaned = [str(e).lower().lstrip(".") for e in raw if str(e).strip()]
        return cleaned if cleaned else DEFAULT_EXTENSIONS[:]
    print(
        f"[WARN] projects.{name}: extensions가 리스트가 아닙니다 ({raw!r}) → 기본값 사용",
        file=sys.stderr,
    )
    return DEFAULT_EXTENSIONS[:]


def _parse_catalog_readme(entry: dict, name: str, catalog: "Path | None") -> "Path | None":
    """
    projects.toml 단일 블록에서 catalog_readme 키를 해석한다.

    - catalog가 None이면 catalog_readme 무시 + 경고
    - 미선언 시 None
    - 선언 시 _resolve_path()로 절대경로 resolve
    """
    raw = entry.get("catalog_readme")
    if raw is None:
        return None
    if catalog is None:
        print(
            f"[WARN] projects.{name}: catalog 미설정 상태에서 catalog_readme 선언 — 무시합니다",
            file=sys.stderr,
        )
        return None
    return _resolve_path(str(raw))


def load_projects(path=PROJECTS_FILE):
    if not path.exists():
        raise FileNotFoundError(f"projects.toml 없음: {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    result = {}
    for name, e in data.get("projects", {}).items():
        vault_active, vault_retention = _parse_vault_cleanup(e, name)
        catalog = _parse_catalog(e, name)
        handbook_sources = _parse_handbook(e, name)
        # handbook 선언 시 catalog 암묵 활성화
        if catalog is None and handbook_sources:
            docs_root_raw = e.get("docs_root")
            if docs_root_raw:
                catalog = _resolve_path(docs_root_raw) / "_wiki"
            else:
                print(
                    f"[WARN] projects.{name}: handbook이 선언되었으나 catalog와 docs_root 모두 없습니다"
                    " → catalog 암묵 활성화 불가. catalog 또는 docs_root를 명시하세요.",
                    file=sys.stderr,
                )
        result[name] = {
            "vault": _resolve_path(e.get("vault")),
            "cold": _resolve_path(e.get("cold")),
            "done": _resolve_path(e.get("done")),
            "docs_root": _resolve_path(e.get("docs_root")),
            # catalog opt-in: None = 비대상, Path = 대상 경로
            "catalog": catalog,
            # vault_cleanup opt-in: {"active": bool, "retention_days": int}
            "vault_cleanup": {
                "active": vault_active,
                "retention_days": vault_retention if vault_active else None,
            },
            # handbook: glob 패턴 지원, 각 항목은 {"path", "writable", "update_when"} dict
            "handbook": handbook_sources,
            # catalog_readme: catalog 설정 시만 유효 (암묵 활성화 반영된 catalog 사용)
            "catalog_readme": _parse_catalog_readme(e, name, catalog),
            # extensions: embed/watch 대상 확장자 목록 (dot 없이 저장)
            "extensions": _parse_extensions(e, name),
            # hot_days: hot 영역 보관 일수 (초과 시 vault로 이동)
            "hot_days": _parse_hot_days(e, name),
            # auto_handbook_update: true 시 handbook-update 무인 자동 실행 (기본 false)
            "auto_handbook_update": _parse_bool_flag(e, "auto_handbook_update", name),
            # auto_catalog_update: true 시 catalog-update 무인 자동 실행 (기본 false)
            "auto_catalog_update": _parse_bool_flag(e, "auto_catalog_update", name),
            # auto_commit: true 시 handbook/catalog 갱신 후 자동 커밋 (기본 false)
            "auto_commit": _parse_bool_flag(e, "auto_commit", name),
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
    cwd = Path(cwd) if cwd else Path(os.environ.get("STASHDEX_CWD", str(Path.cwd())))
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
    # fallback: workspace 기준 첫 세그먼트
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
            "handbook": [
                {
                    "path": str(w["path"]),
                    "writable": w["writable"],
                    "update_when": w["update_when"],
                    "exists": Path(str(w["path"])).exists(),
                }
                for w in cfg.get("handbook", [])
            ],
            "handbook_exists_count": sum(
                1 for w in cfg.get("handbook", []) if Path(str(w["path"])).exists()
            ),
            "catalog_exists": Path(str(cfg["catalog"])).exists() if cfg.get("catalog") else False,
            "catalog_readme": str(cfg["catalog_readme"]) if cfg.get("catalog_readme") else None,
            "extensions": cfg.get("extensions", DEFAULT_EXTENSIONS[:]),
            "hot_days": cfg.get("hot_days", ROTATE_TO_VAULT_DAYS),
            "auto_handbook_update": cfg.get("auto_handbook_update", False),
            "auto_catalog_update": cfg.get("auto_catalog_update", False),
            "auto_commit": cfg.get("auto_commit", False),
        })
    return _json.dumps(result, ensure_ascii=False, indent=2)


def decide_entry_skill(handbook_on: bool, catalog_on: bool) -> "str | None":
    """두 자동화 플래그 조합으로 무인 진입점 스킬 이름을 반환한다.

    플래그 조합과 반환값:

    +-----------------------+----------------------+------------------+
    | auto_handbook_update  | auto_catalog_update  | 반환값           |
    +=======================+======================+==================+
    | False                 | False                | None             |
    +-----------------------+----------------------+------------------+
    | False                 | True                 | "catalog-update" |
    +-----------------------+----------------------+------------------+
    | True                  | False                | "handbook-update"|
    +-----------------------+----------------------+------------------+
    | True                  | True                 | "wiki-update"    |
    +-----------------------+----------------------+------------------+

    None 반환 시 무인 진입점이 없음을 의미한다(제안 모드).
    다른 Phase(B hook, C 헤드리스)가 이 함수를 import해 사용한다.

    Parameters
    ----------
    handbook_on:
        auto_handbook_update 플래그 값
    catalog_on:
        auto_catalog_update 플래그 값

    Returns
    -------
    str | None
        호출할 스킬 이름, 또는 None(무인 없음)
    """
    if handbook_on and catalog_on:
        return "wiki-update"
    if handbook_on:
        return "handbook-update"
    if catalog_on:
        return "catalog-update"
    return None


def get_readonly_handbook_paths(project_name: str) -> set[str]:
    """현재 프로젝트의 writable=false handbook 경로 집합(정규화)을 반환한다.

    PROJECTS[project_name]["handbook"] 항목을 순회하여 차단 대상 경로를 추출한다.
    차단 대상 기준:
    - 객체(dict) 형식 중 writable=False인 항목
    - 문자열 형식 항목 (writable 미지정 = False 취급 — _parse_handbook 규칙과 동일)

    두 경우 모두 _parse_handbook 단계에서 이미 writable=False로 파싱되므로,
    여기서는 w["writable"] is False인 항목만 선별하면 된다.

    경로는 os.path.realpath()로 정규화해 절대경로·심볼릭 링크·상대경로를
    동일한 실체 경로로 비교할 수 있도록 한다.

    반환: 정규화된 차단 대상 경로 문자열의 set (존재하지 않는 경로도 포함).

    사용 예::

        blocked = get_readonly_handbook_paths("my_project")
        if os.path.realpath(target_file) in blocked:
            raise PermissionError(f"{target_file} 은 writable=false handbook 파일입니다.")

    Parameters
    ----------
    project_name:
        PROJECTS 딕셔너리 키. 존재하지 않는 프로젝트명이면 KeyError를 발생시킨다.
    """
    cfg = PROJECTS[project_name]
    handbook_entries: list[dict] = cfg.get("handbook", [])
    blocked: set[str] = set()
    for entry in handbook_entries:
        if not entry.get("writable", False):
            raw_path = entry.get("path")
            if raw_path is not None:
                blocked.add(os.path.realpath(str(raw_path)))
    return blocked


if __name__ == "__main__":
    project = infer_project()
    print(f"현재 프로젝트: {project}")
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT version()")
        print(f"DB 연결 OK: {cur.fetchone()[0][:40]}")

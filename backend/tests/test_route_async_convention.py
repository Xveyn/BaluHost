"""Waechter gegen `async def`-Route-Handler mit sync-DB ohne `await` (#300).

Ein Handler, der `Depends(get_db)` nimmt und nie awaitet, laeuft als
`async def` direkt auf dem Event-Loop und blockiert ihn bei jedem DB-Zugriff.
Als `def` deklariert fuehrt FastAPI ihn im Threadpool aus.

Die Ausnahmeliste `fixtures/async_db_route_allowlist.txt` haelt die heutigen
Treffer fest und darf nur schrumpfen.
"""
import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
ALLOWLIST_PATH = Path(__file__).resolve().parent / "fixtures" / "async_db_route_allowlist.txt"

_ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "api_route"}
_OWN_AWAIT_TYPES = (ast.Await, ast.AsyncWith, ast.AsyncFor)
_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _is_route(fn: ast.AST) -> bool:
    return any(
        isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Attribute)
        and dec.func.attr in _ROUTE_METHODS
        for dec in fn.decorator_list
    )


def _takes_get_db(fn: ast.AST) -> bool:
    for node in ast.walk(fn.args):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Depends"
            and node.args
        ):
            first = node.args[0]
            if isinstance(first, ast.Name) and first.id == "get_db":
                return True
            if isinstance(first, ast.Attribute) and first.attr == "get_db":
                return True
    return False


def _has_own_await(fn: ast.AST) -> bool:
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, _OWN_AWAIT_TYPES):
            return True
        if isinstance(node, _SCOPE_BOUNDARIES):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return False


def find_awaitless_async_db_handlers(source: str, rel: str) -> list[str]:
    tree = ast.parse(source)
    return sorted(
        f"{rel}::{node.name}"
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and _is_route(node)
        and _takes_get_db(node)
        and not _has_own_await(node)
    )


def scan_app() -> set[str]:
    found: set[str] = set()
    for sub in ("api/routes", "plugins/installed"):
        for path in sorted((APP_DIR / sub).rglob("*.py")):
            rel = path.relative_to(APP_DIR).as_posix()
            found.update(
                find_awaitless_async_db_handlers(path.read_text(encoding="utf-8"), rel)
            )
    return found


def load_allowlist() -> set[str]:
    return {
        line.strip()
        for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


SRC = '''
@router.get("/a")
async def flagged(db: Session = Depends(get_db)):
    return db.query(X).all()

@router.get("/b")
async def awaits(db: Session = Depends(get_db)):
    await asyncio.sleep(0)

@router.get("/c")
def sync_ok(db: Session = Depends(get_db)):
    return 1

@router.post("/d")
async def nested_await_only(db: Session = Depends(deps.get_db)):
    async def inner():
        await x()
    return inner

@router.get("/e")
async def no_db(user=Depends(get_current_user)):
    return 1

@router.websocket("/f")
async def ws(db: Session = Depends(get_db)):
    return 1

@router.get("/g")
async def annotated(db: Annotated[Session, Depends(get_db)]):
    return 1
'''


def test_detector_flags_only_awaitless_async_db_handlers():
    assert find_awaitless_async_db_handlers(SRC, "x.py") == [
        "x.py::annotated", "x.py::flagged", "x.py::nested_await_only",
    ]


def test_no_new_awaitless_async_db_handlers():
    new = sorted(scan_app() - load_allowlist())
    assert new == [], (
        "async def + Depends(get_db) ohne await blockiert den Event-Loop. "
        "Als `def` deklarieren (läuft im Threadpool), siehe "
        ".claude/rules/backend/coding-style.md: " + ", ".join(new)
    )


def test_allowlist_has_no_stale_entries():
    stale = sorted(load_allowlist() - scan_app())
    assert stale == [], "Aus tests/fixtures/async_db_route_allowlist.txt entfernen: " + ", ".join(stale)


def test_allowlist_is_sorted_and_unique():
    entries = [l for l in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    assert entries == sorted(set(entries))
